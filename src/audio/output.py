"""Audio output handling for Pi Audio Client."""

import pyaudio
import numpy as np
from typing import Optional
import logging
import wave

logger = logging.getLogger(__name__)


class AudioOutput:
    """Audio output handler for playback."""
    
    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 1024,
        output_device: Optional[str] = None,
        channels: int = 1
    ):
        """Initialize audio output.
        
        Args:
            sample_rate: Sample rate in Hz
            chunk_size: Audio chunk size
            output_device: Device name (None = default)
            channels: Number of audio channels
        """
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
        
        # Get output device or use default
        device_index = None
        if self.output_device:
            for i in range(self._pa.get_device_count()):
                info = self._pa.get_device_info_by_index(i)
                if self.output_device.lower() in info['name'].lower():
                    device_index = i
                    logger.info(f"Using audio output device: {info['name']}")
                    break
        
        if device_index is None:
            logger.info(f"Using default audio output device")
        
        # Open output stream
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
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        
        if self._pa:
            self._pa.terminate()
            self._pa = None
        
        self._playing = False
        logger.debug("Audio output stopped")
    
    def is_playing(self) -> bool:
        """Check if playing."""
        return self._playing
    
    def write_chunk(self, data: np.ndarray) -> None:
        """Write a single chunk of audio data.
        
        Args:
            data: numpy array of audio samples
        """
        if not self._playing:
            raise RuntimeError("Audio output not started")
        
        self._stream.write(data.tobytes())
    
    def write_chunks(self, chunks: list) -> None:
        """Write multiple chunks of audio data.
        
        Args:
            chunks: List of numpy arrays
        """
        for chunk in chunks:
            self.write_chunk(chunk)
    
    def play_file(self, filename: str) -> None:
        """Play audio from WAV file.
        
        Args:
            filename: Input filename
        """
        if not self._playing:
            raise RuntimeError("Audio output not started")
        
        with wave.open(filename, 'rb') as wf:
            data = wf.readframes(self.chunk_size)
            while data:
                self._stream.write(data)
                data = wf.readframes(self.chunk_size)
        
        logger.info(f"Audio file {filename} played")
    
    def play_silence(self, duration: float) -> None:
        """Play silence for specified duration.
        
        Args:
            duration: Duration in seconds
        """
        if not self._playing:
            raise RuntimeError("Audio output not started")
        
        silence = np.zeros(self.chunk_size, dtype=np.int16)
        num_chunks = int((self.sample_rate * duration) / self.chunk_size)
        
        for _ in range(num_chunks):
            self.write_chunk(silence)
        
        logger.debug(f"Silence for {duration}s played")
    
    def get_device_list(self) -> list:
        """Get list of available output devices."""
        if not self._pa:
            self._pa = pyaudio.PyAudio()
        
        devices = []
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if info['maxOutputChannels'] > 0:  # Only output devices
                devices.append({
                    'index': i,
                    'name': info['name'],
                    'channels': info['maxOutputChannels']
                })
        
        return devices