#!/usr/bin/env python3
"""Main entry point for Pi Audio Client.

Connects to hermes-agent on your Mac which handles:
- Audio transcription (whisper tool)
- LLM inference (via model server)
- TTS generation (tts tool)

Interaction model:
- Hold PTT (>0.5s): record and send audio to hermes
- Tap PTT (<0.5s): play next queued response
- Tap Cancel: stop current playback
- Responses queue up and green LED blinks when messages are waiting
"""

import queue
import logging
import subprocess
import signal
import time
from threading import Event, Lock, Thread
from typing import Optional

import numpy as np

from src.config import load_config, Config
from src.gpio import LEDController, ButtonController
from src.audio import AudioInput, AudioOutput
from src.client import HermesClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

RESET_HOLD_SECS = 3.0

class PiAudioClient:
    """Main client for Pi Audio interface."""

    def __init__(self, config: Optional[Config] = None):
        """Initialize Pi Audio Client."""
        self.config = config or load_config()
        self._running = False
        self._shutdown_event = Event()

        # Initialize components
        self.led = LEDController(
            idle_pin=self.config.gpio.led_idle,
            listening_pin=self.config.gpio.led_listening
        )

        self.buttons = ButtonController(
            ptt_pin=self.config.gpio.button_ptt,
            cancel_pin=self.config.gpio.button_cancel
        )

        self.audio_input = AudioInput(
            sample_rate=self.config.audio.sample_rate,
            chunk_size=self.config.audio.chunk_size,
            input_device=self.config.audio.input_device
        )

        self.audio_output = AudioOutput(
            sample_rate=self.config.audio.sample_rate,
            chunk_size=self.config.audio.chunk_size,
            output_device=self.config.audio.output_device
        )

        self.hermes = HermesClient(
            url=self.config.server.url,
            api_key=self.config.server.api_key,
            device_id=self.config.server.device_id,
        )

        # Recording state
        self._recording = False
        self._recording_buffer = []
        self._buffer_lock = Lock()
        self._press_time = 0.0
        self._record_thread: Optional[Thread] = None
        self._dual_hold_started_at: Optional[float] = None
        self._dual_hold_triggered = False

        # Playback state
        self._playing = False
        self._stop_playback = Event()
        self._last_audio: Optional[np.ndarray] = None
        self._playback_state_lock = Lock()
        self._playback_lock = Lock()
        self._playback_scheduled = False

        # Message queue — hermes responses waiting to be played
        self._message_queue: queue.Queue = queue.Queue()
        self._pending_count = 0
        self._pending_lock = Lock()

    def setup(self) -> None:
        """Setup all components."""
        logger.info("Setting up Pi Audio Client...")

        self.audio_input.start()
        self.audio_output.start()

        # Cancel button callback (cancel is fine as callback — it's simple)
        if self.buttons.cancel_button:
            self.buttons.set_cancel_callback(self._on_cancel_pressed)

        self.led.set_idle()

        if not self.hermes.health_check():
            logger.warning("Hermes server not reachable!")

        logger.info("Setup complete")

    # ------------------------------------------------------------------
    # PTT: hold to record
    # ------------------------------------------------------------------

    def _on_ptt_pressed(self) -> None:
        """Handle PTT button press — note the time, don't record yet."""
        self._press_time = time.time()
        self._recording = False
        self._record_thread = None
        logger.debug("PTT pressed")

    def _start_recording(self) -> None:
        """Start recording after hold threshold is reached."""
        logger.info("PTT held — recording")
        self._recording = True
        self.led.set_listening()
        with self._buffer_lock:
            self._recording_buffer = []
        self._record_thread = Thread(target=self._record_loop, daemon=True)
        self._record_thread.start()

    def _record_loop(self) -> None:
        """Read audio chunks while recording (runs in dedicated thread)."""
        max_chunks = int(
            (self.config.audio.sample_rate * self.config.state.max_recording_secs)
            / self.config.audio.chunk_size
        )
        chunks_read = 0
        while self._recording and not self._shutdown_event.is_set():
            try:
                chunk = self.audio_input.read_chunk()
                with self._buffer_lock:
                    if self._recording:
                        self._recording_buffer.append(chunk)
                chunks_read += 1
                if chunks_read >= max_chunks:
                    logger.warning("Recording capped at %ds", self.config.state.max_recording_secs)
                    self._recording = False
                    break
            except Exception as e:
                logger.error(f"Recording error: {e}")
                break

    def _on_ptt_released(self) -> None:
        """Handle PTT release — either send audio (hold) or play message (tap)."""
        hold_time = time.time() - self._press_time

        # Tap: play next queued message
        if not self._recording:
            logger.info("PTT tap (%.2fs) — play next message", hold_time)
            self._play_next_message()
            return

        # Hold: stop recording and send to hermes
        self._recording = False

        if self._record_thread:
            self._record_thread.join(timeout=1.0)

        with self._buffer_lock:
            buffer = list(self._recording_buffer)
            self._recording_buffer = []

        if not buffer:
            logger.warning("No audio recorded")
            self._update_led()
            return

        audio_data = np.concatenate(buffer)
        duration = len(audio_data) / self.config.audio.sample_rate
        logger.info("Sending %.1fs audio to hermes", duration)

        self.led.set_processing()

        with self._pending_lock:
            self._pending_count += 1

        # Send in background — don't block the polling loop
        thread = Thread(target=self._hermes_worker, args=(audio_data,), daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # PTT tap: play next queued message
    # ------------------------------------------------------------------

    def _play_next_message(self) -> None:
        """Play the next message from the queue."""
        if not self._reserve_playback_slot():
            logger.info("Playback already in progress")
            return
        try:
            text, audio = self._message_queue.get_nowait()
        except queue.Empty:
            logger.info("No messages to play")
            self._release_playback_slot()
            self._update_led()
            return

        if self.config.debug_log_transcripts:
            logger.info("Playing: %s", text[:80])
        else:
            logger.info("Playing queued response")
        self._spawn_playback_thread(audio)

    # ------------------------------------------------------------------
    # Cancel button
    # ------------------------------------------------------------------

    def _on_cancel_pressed(self) -> None:
        """Cancel button — stop playback if playing, otherwise replay last."""
        with self._playback_state_lock:
            if self._playing:
                logger.info("Stopping playback")
                self._stop_playback.set()
                return

            if self._last_audio is None or len(self._last_audio) == 0:
                logger.info("Cancel — nothing to replay")
                return

            replay_audio = self._last_audio
        if not self._reserve_playback_slot():
            logger.info("Playback already in progress")
            return

        logger.info("Replaying last response")
        self._spawn_playback_thread(replay_audio)

    def _handle_dual_button_reset(
        self,
        ptt_pressed: bool,
        cancel_pressed: bool,
        now: Optional[float] = None,
    ) -> bool:
        """Detect a long press on both buttons and reboot the Pi.

        Returns True when normal single-button handling should be suppressed.
        """
        if not cancel_pressed or not ptt_pressed:
            self._dual_hold_started_at = None
            self._dual_hold_triggered = False
            return False

        if self._dual_hold_triggered:
            return True

        now = now if now is not None else time.time()
        if self._dual_hold_started_at is None:
            self._dual_hold_started_at = now
            logger.info("Both buttons pressed — hold for %.1fs to reboot", RESET_HOLD_SECS)
            return True

        if now - self._dual_hold_started_at < RESET_HOLD_SECS:
            return True

        self._dual_hold_triggered = True
        self._trigger_system_reset()
        return True

    def _trigger_system_reset(self) -> None:
        """Reboot the Pi after a deliberate dual-button hold."""
        logger.warning("Dual-button reset triggered — rebooting system")
        self._stop_playback.set()
        self._shutdown_event.set()
        try:
            self.led.set_error()
        except Exception:
            logger.exception("Failed to set error LED before reboot")
        Thread(target=self._reboot_system, daemon=True).start()

    def _reboot_system(self) -> None:
        """Issue the reboot command in a background thread."""
        try:
            subprocess.run(["sudo", "reboot"], check=True)
        except Exception:
            logger.exception("Failed to reboot system")

    # ------------------------------------------------------------------
    # Hermes worker (background thread)
    # ------------------------------------------------------------------

    def _hermes_worker(self, audio_data: np.ndarray) -> None:
        """Send audio to hermes and queue the response."""
        try:
            response_text, tts_audio = self.hermes.send_audio_and_get_response(
                audio_data,
                self.config.audio.sample_rate
            )

            if self.config.debug_log_transcripts:
                logger.info("Response: %s", response_text[:100])
            else:
                logger.info("Received response from hermes")

            if len(tts_audio) > 0:
                self._message_queue.put((response_text, tts_audio))
                logger.info("Message queued (%d waiting)", self._message_queue.qsize())
            else:
                logger.warning("No TTS audio in response")

        except Exception as e:
            logger.error("Hermes error: %s", e, exc_info=True)

        finally:
            with self._pending_lock:
                self._pending_count -= 1
            self._update_led()

    # ------------------------------------------------------------------
    # Audio playback
    # ------------------------------------------------------------------

    def _reserve_playback_slot(self) -> bool:
        """Reserve the playback worker so only one playback can be scheduled at a time."""
        with self._playback_state_lock:
            if self._playing or self._playback_scheduled:
                return False
            self._playback_scheduled = True
            return True

    def _release_playback_slot(self) -> None:
        """Release a playback slot when no worker was started."""
        with self._playback_state_lock:
            self._playback_scheduled = False

    def _spawn_playback_thread(self, audio_data: np.ndarray) -> None:
        """Start a playback worker after a slot has been reserved."""
        Thread(target=self._play_response, args=(audio_data,), daemon=True).start()

    def _play_response(self, audio_data: np.ndarray) -> None:
        """Play audio response through speaker."""
        with self._playback_lock:
            with self._playback_state_lock:
                self._playback_scheduled = False
                self._playing = True

            self._stop_playback.clear()
            self._last_audio = audio_data
            self.led.set_speaking()

            try:
                chunk_size = self.config.audio.chunk_size
                for i in range(0, len(audio_data), chunk_size):
                    if self._shutdown_event.is_set() or self._stop_playback.is_set():
                        logger.info("Playback stopped")
                        break
                    chunk = audio_data[i:i + chunk_size]
                    self.audio_output.write_chunk(chunk)
            finally:
                with self._playback_state_lock:
                    self._playing = False
                self._update_led()

    # ------------------------------------------------------------------
    # LED state management
    # ------------------------------------------------------------------

    def _update_led(self) -> None:
        """Set LED based on current state."""
        if self._recording:
            self.led.set_listening()
        elif self._playing:
            self.led.set_speaking()
        elif not self._message_queue.empty():
            self.led.set_message_waiting()
        elif self._pending_count > 0:
            self.led.set_processing()
        else:
            self.led.set_idle()

    # ------------------------------------------------------------------
    # Main loop — polling, no GPIO callbacks for PTT
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Run the main loop.

        Polls PTT button state every 20ms. Recording runs in a
        dedicated thread. No GPIO callbacks for PTT — polling is
        more reliable on Pi Zero W.
        """
        logger.info("Starting Pi Audio Client...")
        self.setup()
        self._running = True

        logger.info("Ready — hold PTT to speak, tap PTT to play messages")

        was_pressed = False
        while not self._shutdown_event.is_set():
            pressed = self.buttons.ptt_button.is_pressed
            cancel_pressed = (
                self.buttons.cancel_button.is_pressed if self.buttons.cancel_button else False
            )

            if self._handle_dual_button_reset(pressed, cancel_pressed):
                was_pressed = pressed
                time.sleep(0.02)
                continue

            if pressed and not was_pressed:
                self._on_ptt_pressed()
            elif pressed and not self._recording and self._press_time > 0:
                # Still holding — start recording once past threshold
                if time.time() - self._press_time >= self.config.state.hold_threshold:
                    self._start_recording()
            elif was_pressed and not pressed:
                self._on_ptt_released()
                self._press_time = 0.0

            was_pressed = pressed
            time.sleep(0.02)

        logger.info("Shutting down...")
        self.cleanup()

    def cleanup(self) -> None:
        """Clean up all resources."""
        logger.info("Cleaning up...")

        self._running = False
        self._recording = False
        self._shutdown_event.set()
        self._stop_playback.set()

        self.hermes.close()
        self.audio_input.stop()
        self.audio_output.stop()
        self.buttons.cleanup()
        self.led.cleanup()

        logger.info("Cleanup complete")


def main():
    """Main entry point."""
    config = load_config()
    logger.info(f"Loaded config: {config}")

    client: Optional[PiAudioClient] = None

    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        if client is not None:
            client._shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        client = PiAudioClient(config)
        client.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception:
        logger.exception("Pi Audio Client crashed")
        if client is not None:
            try:
                client.led.set_error()
                time.sleep(10)
            except Exception:
                logger.exception("Failed to signal error state on LED")
    finally:
        if client is not None:
            client.cleanup()


if __name__ == "__main__":
    main()
