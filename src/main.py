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
from threading import Thread, Event
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
        self._recording_buffer = []
        
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
        """Handle PTT button press."""
        logger.info("PTT pressed - starting recording")
        self.led.set_listening()
        self._recording_buffer = []
        
    def _on_ptt_released(self) -> None:
        """Handle PTT button release."""
        logger.info("PTT released - processing audio")
        self._process_audio()
    
    def _on_cancel_pressed(self) -> None:
        """Handle cancel button press."""
        logger.info("Cancel pressed - stopping recording")
        self._recording_buffer = []
        self.led.set_idle()
    
    def _process_audio(self) -> None:
        """Process recorded audio."""
        if not self._recording_buffer:
            logger.warning("No audio to process")
            self.led.set_idle()
            return
        
        # Concatenate all chunks
        audio_data = np.concatenate(self._recording_buffer)
        self._recording_buffer = []
        
        logger.info(f"Processing {len(audio_data)} samples...")
        
        try:
            # Send to hermes and get response
            response_text, tts_audio = self.hermes.send_audio_and_get_response(
                audio_data,
                self.config.audio.sample_rate
            )
            
            # Update state
            self.led.set_processing()
            
            # Speak response
            self.led.set_speaking()
            self._play_audio(tts_audio)
            
            # Back to idle
            self.led.set_idle()
            
            # Update activity
            self._last_activity = time.time()
            
        except Exception as e:
            logger.error(f"Error processing audio: {e}")
            self.led.set_error()
            time.sleep(2)
            self.led.set_idle()
    
    def _play_audio(self, audio_data: np.ndarray) -> None:
        """Play audio data."""
        # Split into chunks and play
        chunk_size = self.config.audio.chunk_size
        for i in range(0, len(audio_data), chunk_size):
            if self._shutdown_event.is_set():
                break
            chunk = audio_data[i:i+chunk_size]
            self.audio_output.write_chunk(chunk)
    
    def run(self) -> None:
        """Run the main loop."""
        logger.info("Starting Pi Audio Client...")
        self.setup()
        self._running = True
        
        # Wait for PTT press
        logger.info("Press PTT button to speak...")
        
        while not self._shutdown_event.is_set():
            if self.buttons.is_ptt_pressed():
                # Collect audio while PTT is pressed
                self._recording_buffer.append(
                    self.audio_input.read_chunk()
                )
                
                # Check for timeout
                if len(self._recording_buffer) * self.config.audio.chunk_size > \
                   self.config.audio.sample_rate * self.config.state.timeout_recording:
                    logger.warning("Recording timeout - stopping")
                    self._recording_buffer = []
                    self.led.set_idle()
            else:
                # Brief pause when not recording
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
    
    def start_background_thread(self) -> Thread:
        """Start client in background thread."""
        thread = Thread(target=self.run, daemon=True)
        thread.start()
        return thread


def main():
    """Main entry point."""
    # Load config
    config = load_config()
    logger.info(f"Loaded config: {config}")
    
    # Create client
    client = PiAudioClient(config)
    
    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        client._shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run client
    try:
        client.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        client.cleanup()


if __name__ == "__main__":
    main()