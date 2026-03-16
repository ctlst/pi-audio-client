#!/usr/bin/env python3
"""Main entry point for Pi Audio Client.

Connects to hermes-agent on your Mac (100.96.134.76) which handles:
- Audio transcription (whisper tool)
- LLM inference (via model server)
- TTS generation (tts tool)
"""

import logging
import sys
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

    def setup(self) -> None:
        """Setup all components."""
        logger.info("Setting up Pi Audio Client...")

        # Start audio
        self.audio_input.start()
        self.audio_output.start()

        # Setup button callbacks
        self.buttons.set_ptt_callback(self._on_ptt_pressed)
        self.buttons.ptt_button.when_released = self._on_ptt_released
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
        self._recording = True
        self.led.set_listening()
        with self._buffer_lock:
            self._recording_buffer = []

    def _on_ptt_released(self) -> None:
        """Handle PTT button release (GPIO callback thread).

        Grabs whatever is in the buffer and processes it.
        Ignores false releases (empty buffer = noise, stay recording).
        """
        if not self._recording:
            return

        with self._buffer_lock:
            if not self._recording_buffer:
                # False release from noisy GPIO — ignore it, keep recording
                logger.debug("Ignoring false release (empty buffer)")
                return
            buffer = list(self._recording_buffer)
            self._recording_buffer = []

        self._recording = False
        logger.info("PTT released - processing audio")

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
            logger.error(f"Error processing audio: {e}")
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

        The main loop continuously reads audio chunks while _recording is True.
        PTT press/release are handled by GPIO callbacks on a separate thread.
        The release callback grabs the buffer and processes it.
        """
        logger.info("Starting Pi Audio Client...")
        self.setup()
        self._running = True

        logger.info("Ready — press and hold PTT to speak")

        while not self._shutdown_event.is_set():
            if self._recording:
                chunk = self.audio_input.read_chunk()
                with self._buffer_lock:
                    if self._recording:  # double-check under lock
                        self._recording_buffer.append(chunk)

                # Check for timeout
                with self._buffer_lock:
                    total = len(self._recording_buffer) * self.config.audio.chunk_size
                if total > self.config.audio.sample_rate * self.config.state.timeout_recording:
                    logger.warning("Recording timeout - stopping")
                    self._recording = False
                    with self._buffer_lock:
                        self._recording_buffer = []
                    self.led.set_idle()
            else:
                time.sleep(0.01)

        logger.info("Shutting down...")
        self.cleanup()

    def cleanup(self) -> None:
        """Clean up all resources."""
        logger.info("Cleaning up...")

        self._running = False
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
