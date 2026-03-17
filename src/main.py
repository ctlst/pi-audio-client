#!/usr/bin/env python3
"""Main entry point for Pi Audio Client.

Connects to hermes-agent on your Mac which handles:
- Audio transcription (whisper tool)
- LLM inference (via model server)
- TTS generation (tts tool)
"""

import logging
import signal
import time
from threading import Thread, Event, Lock
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

        # State tracking
        self._last_activity = time.time()
        self._recording = False
        self._recording_buffer = []
        self._buffer_lock = Lock()
        self._press_time = 0.0
        self._record_thread: Optional[Thread] = None

    def setup(self) -> None:
        """Setup all components."""
        logger.info("Setting up Pi Audio Client...")

        # Start audio
        self.audio_input.start()
        self.audio_output.start()

        # Cancel button callback
        if self.buttons.cancel_button:
            self.buttons.set_cancel_callback(self._on_cancel_pressed)

        # Set initial state
        self.led.set_idle()

        # Health check
        if not self.hermes.health_check():
            logger.warning("Hermes server not reachable!")

        logger.info("Setup complete")

    def _on_ptt_pressed(self) -> None:
        """Handle PTT button press (GPIO callback thread)."""
        logger.info("PTT pressed - starting recording")
        self._press_time = time.time()
        self._recording = True
        self.led.set_listening()
        with self._buffer_lock:
            self._recording_buffer = []
        # Start recording thread — reads audio in background
        self._record_thread = Thread(target=self._record_loop, daemon=True)
        self._record_thread.start()

    def _record_loop(self) -> None:
        """Read audio chunks while recording (runs in dedicated thread)."""
        while self._recording and not self._shutdown_event.is_set():
            try:
                chunk = self.audio_input.read_chunk()
                with self._buffer_lock:
                    if self._recording:
                        self._recording_buffer.append(chunk)
            except Exception as e:
                logger.error(f"Recording error: {e}")
                break

    def _on_ptt_released(self) -> None:
        """Handle PTT button release (GPIO callback thread)."""
        if not self._recording:
            return

        hold_time = time.time() - self._press_time
        self._recording = False

        # Wait for record thread to finish its current read
        if self._record_thread:
            self._record_thread.join(timeout=1.0)

        with self._buffer_lock:
            buffer = list(self._recording_buffer)
            self._recording_buffer = []

        if not buffer or hold_time < 0.3:
            logger.debug("Ignoring short press (%.2fs, %d chunks)", hold_time, len(buffer))
            self.led.set_idle()
            return

        logger.info("PTT released - processing audio (held %.1fs)", hold_time)

        audio_data = np.concatenate(buffer)
        duration = len(audio_data) / self.config.audio.sample_rate
        logger.info(f"Processing {len(audio_data)} samples ({duration:.1f}s)")

        self.led.set_processing()

        try:
            response_text, tts_audio = self.hermes.send_audio_and_get_response(
                audio_data,
                self.config.audio.sample_rate
            )

            logger.info(f"Response: {response_text[:100]}")

            if len(tts_audio) > 0:
                logger.info(f"Playing {len(tts_audio)} samples ({len(tts_audio)/self.config.audio.sample_rate:.1f}s)")
                self.led.set_speaking()
                self._play_audio(tts_audio)
            else:
                logger.warning("No TTS audio received — nothing to play")

            self.led.set_idle()
            self._last_activity = time.time()

        except Exception as e:
            logger.error(f"Error processing audio: {e}", exc_info=True)
            self.led.set_error()
            time.sleep(2)
            self.led.set_idle()

    def _on_cancel_pressed(self) -> None:
        """Handle cancel button press."""
        logger.info("Cancel pressed - stopping recording")
        self._recording = False
        with self._buffer_lock:
            self._recording_buffer = []
        self.led.set_idle()

    def _play_audio(self, audio_data: np.ndarray) -> None:
        """Play audio data."""
        chunk_size = self.config.audio.chunk_size
        for i in range(0, len(audio_data), chunk_size):
            if self._shutdown_event.is_set():
                break
            chunk = audio_data[i:i+chunk_size]
            self.audio_output.write_chunk(chunk)

    def run(self) -> None:
        """Run the main loop.

        Polls PTT button state every 20ms. Recording runs in a
        dedicated thread. No GPIO callbacks for PTT — polling is
        more reliable on noisy wiring.
        """
        logger.info("Starting Pi Audio Client...")
        self.setup()
        self._running = True

        logger.info("Ready — press and hold PTT to speak")

        was_pressed = False
        while not self._shutdown_event.is_set():
            pressed = self.buttons.ptt_button.is_pressed

            if pressed and not was_pressed:
                self._on_ptt_pressed()
            elif was_pressed and not pressed and self._recording:
                self._on_ptt_released()

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
