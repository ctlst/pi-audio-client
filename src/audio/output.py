"""Audio output handling for Pi Audio Client."""

import pyaudio
import numpy as np
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class AudioOutput:
    """Audio output handler using blocking writes."""

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        output_device: Optional[str] = None,
        channels: int = 1
    ):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.output_device = output_device
        self.channels = channels
        self._pa: Optional[pyaudio.PyAudio] = None
        self._stream: Optional[pyaudio.Stream] = None
        self._playing = False

    def start(self) -> None:
        """Start audio output."""
        self._pa = pyaudio.PyAudio()

        device_index = None
        if self.output_device:
            for i in range(self._pa.get_device_count()):
                info = self._pa.get_device_info_by_index(i)
                if self.output_device.lower() in info['name'].lower():
                    device_index = i
                    logger.info(f"Using audio output device: {info['name']}")
                    break

        if device_index is None:
            logger.info("Using default audio output device")

        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self.channels,
            rate=self.sample_rate,
            output=True,
            frames_per_buffer=self.chunk_size,
            output_device_index=device_index
        )

        self._playing = True
        logger.debug("Audio output started")

    def stop(self) -> None:
        """Stop audio output."""
        self._playing = False
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa:
            self._pa.terminate()
            self._pa = None
        logger.debug("Audio output stopped")

    def is_playing(self) -> bool:
        return self._playing

    def drain(self) -> None:
        """No-op for blocking mode."""
        pass

    def write_chunk(self, data: np.ndarray) -> None:
        """Write a chunk of audio data (blocking)."""
        if not self._playing:
            raise RuntimeError("Audio output not started")
        self._stream.write(data.tobytes())

    def get_device_list(self) -> list:
        if not self._pa:
            self._pa = pyaudio.PyAudio()
        devices = []
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if info['maxOutputChannels'] > 0:
                devices.append({
                    'index': i,
                    'name': info['name'],
                    'channels': info['maxOutputChannels']
                })
        return devices
