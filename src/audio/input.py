"""Audio input handling for Pi Audio Client."""

import pyaudio
import numpy as np
from typing import Optional, Generator
import logging

logger = logging.getLogger(__name__)


class AudioInput:
    """Audio input handler for recording audio."""

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        input_device: Optional[str] = None,
        channels: int = 1
    ):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.input_device = input_device
        self.channels = channels
        self._pa: Optional[pyaudio.PyAudio] = None
        self._stream: Optional[pyaudio.Stream] = None
        self._recording = False

    def start(self) -> None:
        """Start audio input."""
        self._pa = pyaudio.PyAudio()

        device_index = None
        if self.input_device:
            for i in range(self._pa.get_device_count()):
                info = self._pa.get_device_info_by_index(i)
                if self.input_device.lower() in info['name'].lower():
                    device_index = i
                    logger.info(f"Using audio input device: {info['name']}")
                    break

        if device_index is None:
            logger.info("Using default audio input device")

        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            input_device_index=device_index
        )

        self._recording = True
        logger.debug("Audio input started")

    def stop(self) -> None:
        """Stop audio input."""
        if self._stream:
            try:
                self._stream.stop_stream()
            finally:
                self._stream.close()
            self._stream = None
        if self._pa:
            self._pa.terminate()
            self._pa = None
        self._recording = False
        logger.debug("Audio input stopped")

    def restart(self) -> None:
        """Reinitialize the input stream after a capture fault."""
        logger.warning("Restarting audio input stream")
        self.stop()
        self.start()

    def is_recording(self) -> bool:
        return self._recording

    def read_chunk(self) -> np.ndarray:
        """Read a single chunk of audio data."""
        if not self._recording:
            raise RuntimeError("Audio input not started")
        data = self._stream.read(self.chunk_size, exception_on_overflow=False)
        return np.frombuffer(data, dtype=np.int16)

    def read_chunks(self, duration: float) -> Generator[np.ndarray, None, None]:
        num_chunks = int((self.sample_rate * duration) / self.chunk_size)
        for _ in range(num_chunks):
            yield self.read_chunk()

    def get_device_list(self) -> list:
        if not self._pa:
            self._pa = pyaudio.PyAudio()
        devices = []
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                devices.append({
                    'index': i,
                    'name': info['name'],
                    'channels': info['maxInputChannels']
                })
        return devices
