#!/usr/bin/env python3
"""Main entry point for Pi Audio Client.

Connects to hermes-agent on your Mac which handles:
- Audio transcription (Whisper STT)
- LLM inference (via configured model)
- TTS generation (Edge TTS / ElevenLabs / OpenAI)

Interaction model:
- Hold PTT: record and send audio to hermes
- Tap PTT: play next queued response
- Tap Cancel: stop current playback
- Double-tap Cancel: replay last response
- Responses queue up and green LED blinks when messages are waiting
"""

import logging
import signal
import time
import queue
from threading import Thread, Event, Lock
from typing import Optional

import numpy as np

from src.config import load_config, Config
from src.gpio import LEDController
from src.gpio.taps import TapDetector
from src.audio import AudioInput, AudioOutput
from src.client import HermesClient

from gpiozero import Button

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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

        # Raw buttons — TapDetector wires callbacks
        self.ptt_button = Button(
            self.config.gpio.button_ptt, pull_up=True, bounce_time=0.3
        )
        self.cancel_button = Button(
            self.config.gpio.button_cancel, pull_up=True, bounce_time=0.1
        ) if self.config.gpio.button_cancel else None

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

        # State
        self._recording = False
        self._recording_buffer = []
        self._buffer_lock = Lock()
        self._playing = False
        self._stop_playback = Event()

        # Message queue — hermes responses waiting to be played
        self._message_queue: queue.Queue = queue.Queue()
        self._last_audio: Optional[np.ndarray] = None
        self._pending_count = 0
        self._pending_lock = Lock()

    def setup(self) -> None:
        """Setup all components."""
        logger.info("Setting up Pi Audio Client...")

        # Start audio
        self.audio_input.start()
        self.audio_output.start()

        # PTT button: hold to record, tap to play next message
        self.ptt_tap = TapDetector(
            self.ptt_button,
            on_hold=self._on_ptt_hold,
            on_hold_release=self._on_ptt_release,
            on_single_tap=self._on_ptt_tap,
            hold_threshold=0.5,
        )

        # Cancel button: tap to stop, double-tap to replay
        if self.cancel_button:
            self.cancel_tap = TapDetector(
                self.cancel_button,
                on_single_tap=self._on_cancel_tap,
                on_double_tap=self._on_cancel_double_tap,
                hold_threshold=1.0,
            )

        # Set initial state
        self.led.set_idle()

        # Health check
        if not self.hermes.health_check():
            logger.warning("Hermes server not reachable!")

        logger.info("Setup complete")

    # ------------------------------------------------------------------
    # PTT button handlers
    # ------------------------------------------------------------------

    def _on_ptt_hold(self) -> None:
        """PTT held — start recording."""
        logger.info("PTT hold — recording")
        self._recording = True
        self.led.set_listening()
        with self._buffer_lock:
            self._recording_buffer = []

    def _on_ptt_release(self) -> None:
        """PTT released after hold — send audio to hermes."""
        if not self._recording:
            return
        self._recording = False

        with self._buffer_lock:
            buffer = list(self._recording_buffer)
            self._recording_buffer = []

        if not buffer:
            logger.warning("No audio recorded")
            self._update_led()
            return

        audio_data = np.concatenate(buffer)
        duration = len(audio_data) / self.config.audio.sample_rate
        logger.info(f"Sending {duration:.1f}s audio to hermes")

        # Show processing
        self.led.set_processing()

        # Track pending requests
        with self._pending_lock:
            self._pending_count += 1

        # Send to hermes in background thread
        thread = Thread(target=self._hermes_worker, args=(audio_data,), daemon=True)
        thread.start()

    def _on_ptt_tap(self) -> None:
        """PTT tapped — play next queued message."""
        if self._message_queue.empty():
            logger.info("PTT tap — no messages to play")
            return

        text, audio = self._message_queue.get()
        logger.info(f"Playing: {text[:80]}")
        self._play_response(audio)

    # ------------------------------------------------------------------
    # Cancel button handlers
    # ------------------------------------------------------------------

    def _on_cancel_tap(self) -> None:
        """Cancel tapped — stop current playback."""
        if self._playing:
            logger.info("Stop playback")
            self._stop_playback.set()
        else:
            logger.info("Cancel tap — nothing playing")

    def _on_cancel_double_tap(self) -> None:
        """Cancel double-tapped — replay last response."""
        if self._last_audio is not None and len(self._last_audio) > 0:
            logger.info("Replaying last response")
            self._play_response(self._last_audio)
        else:
            logger.info("Double tap — no previous response to replay")

    # ------------------------------------------------------------------
    # Hermes worker (runs in background thread)
    # ------------------------------------------------------------------

    def _hermes_worker(self, audio_data: np.ndarray) -> None:
        """Send audio to hermes and queue the response."""
        try:
            response_text, tts_audio = self.hermes.send_audio_and_get_response(
                audio_data,
                self.config.audio.sample_rate
            )

            logger.info(f"Response received: {response_text[:80]}")

            if len(tts_audio) > 0:
                self._message_queue.put((response_text, tts_audio))
                logger.info("Message queued (%d in queue)", self._message_queue.qsize())
            else:
                logger.warning("No TTS audio in response")

        except Exception as e:
            logger.error(f"Hermes error: {e}")

        finally:
            with self._pending_lock:
                self._pending_count -= 1
            self._update_led()

    # ------------------------------------------------------------------
    # Audio playback
    # ------------------------------------------------------------------

    def _play_response(self, audio_data: np.ndarray) -> None:
        """Play audio response through speaker."""
        self._playing = True
        self._stop_playback.clear()
        self._last_audio = audio_data
        self.led.set_speaking()

        chunk_size = self.config.audio.chunk_size
        for i in range(0, len(audio_data), chunk_size):
            if self._shutdown_event.is_set() or self._stop_playback.is_set():
                logger.info("Playback stopped")
                break
            chunk = audio_data[i:i + chunk_size]
            self.audio_output.write_chunk(chunk)

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
            # New messages waiting — blink green
            self.led.set_speaking()  # blinks green
        elif self._pending_count > 0:
            self.led.set_processing()
        else:
            self.led.set_idle()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Run the main loop.

        Continuously reads audio while recording. Button actions are
        handled by TapDetector callbacks on GPIO threads. Hermes calls
        run in background threads. Main loop just collects audio and
        updates LED state.
        """
        logger.info("Starting Pi Audio Client...")
        self.setup()
        self._running = True

        logger.info("Ready — hold PTT to speak, tap PTT to play messages")

        while not self._shutdown_event.is_set():
            if self._recording:
                chunk = self.audio_input.read_chunk()
                with self._buffer_lock:
                    if self._recording:
                        self._recording_buffer.append(chunk)

                # Timeout check
                with self._buffer_lock:
                    total = len(self._recording_buffer) * self.config.audio.chunk_size
                if total > self.config.audio.sample_rate * self.config.state.timeout_recording:
                    logger.warning("Recording timeout")
                    self._recording = False
                    with self._buffer_lock:
                        self._recording_buffer = []
                    self._update_led()
            else:
                time.sleep(0.02)

        logger.info("Shutting down...")
        self.cleanup()

    def cleanup(self) -> None:
        """Clean up all resources."""
        logger.info("Cleaning up...")

        self._running = False
        self._shutdown_event.set()
        self._stop_playback.set()

        self.hermes.close()
        self.audio_input.stop()
        self.audio_output.stop()
        self.ptt_tap.cleanup()
        if self.cancel_button:
            self.cancel_tap.cleanup()
        self.ptt_button.close()
        if self.cancel_button:
            self.cancel_button.close()
        self.led.cleanup()

        logger.info("Cleanup complete")


def main():
    """Main entry point."""
    config = load_config()
    logger.info(f"Loaded config: {config}")

    client = PiAudioClient(config)

    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        client._shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        client.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        client.cleanup()


if __name__ == "__main__":
    main()
