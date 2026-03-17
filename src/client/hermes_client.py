"""Hermes gateway client for Pi Audio Client.

Connects to the hermes gateway Pi adapter (running on your Mac) which handles:
- Audio transcription (Whisper STT)
- LLM inference (via configured model)
- TTS generation (Edge TTS / ElevenLabs / OpenAI)

The Pi sends raw WAV audio, the gateway processes the full pipeline,
and returns JSON with text + an audio URL to fetch.
"""

import io
import wave
import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import requests

logger = logging.getLogger(__name__)


class HermesClient:
    """Client for the hermes gateway Pi adapter."""

    def __init__(
        self,
        url: str,
        api_key: Optional[str] = None,
        device_id: str = "pi-audio-1",
    ):
        """Initialize hermes client.

        Args:
            url: Gateway base URL (e.g., http://your-mac-ip:8099)
            api_key: Optional API key for authentication
            device_id: Unique device identifier for session tracking
        """
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.device_id = device_id
        self._session = requests.Session()

        if api_key:
            self._session.headers["Authorization"] = f"Bearer {api_key}"
        self._session.headers["X-Device-ID"] = device_id

        logger.info("Hermes client initialized: %s (device=%s)", url, device_id)

    def send_audio_and_get_response(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        chat_id: Optional[str] = None,
    ) -> Tuple[str, np.ndarray]:
        """Send audio and get response with TTS audio.

        Posts raw WAV to the Pi adapter, which runs the full pipeline
        (STT -> LLM -> TTS) and returns JSON with text + audio_url.

        Args:
            audio_data: Audio samples as numpy array (16-bit PCM)
            sample_rate: Sample rate in Hz
            chat_id: Unused, kept for API compatibility

        Returns:
            Tuple of (response text, TTS audio as numpy array)
        """
        # Encode audio as WAV
        wav_bytes = self._encode_wav(audio_data, sample_rate)

        # POST to Pi adapter
        response = self._session.post(
            f"{self.url}/pi/audio",
            data=wav_bytes,
            headers={"Content-Type": "audio/wav"},
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()

        response_text = data.get("text", "")
        logger.info("Response: %s", response_text[:100])

        # Fetch TTS audio if available
        audio_url = data.get("audio_url")
        if audio_url:
            tts_audio = self._fetch_audio(audio_url, sample_rate)
        else:
            tts_audio = np.array([], dtype=np.int16)

        return response_text, tts_audio

    def health_check(self) -> bool:
        """Check if the hermes gateway Pi adapter is reachable."""
        try:
            response = self._session.get(f"{self.url}/pi/health", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error("Health check failed: %s", e)
            return False

    def close(self) -> None:
        """Close client session."""
        self._session.close()
        logger.debug("Hermes client closed")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_wav(audio_data: np.ndarray, sample_rate: int) -> bytes:
        """Encode numpy audio array as WAV bytes."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data.astype(np.int16).tobytes())
        return buf.getvalue()

    def _fetch_audio(self, audio_url: str, sample_rate: int) -> np.ndarray:
        """Fetch TTS audio from a URL and decode to numpy array.

        Handles WAV, OGG/Opus, MP3, and raw PCM responses.
        """
        # If relative URL, prepend base
        if audio_url.startswith("/"):
            audio_url = f"{self.url}{audio_url}"

        resp = self._session.get(audio_url, timeout=30)
        resp.raise_for_status()
        audio_bytes = resp.content

        content_type = resp.headers.get("Content-Type", "")
        url_lower = audio_url.lower()

        # WAV
        if content_type.startswith("audio/wav") or audio_bytes[:4] == b"RIFF":
            return self._decode_wav(audio_bytes)

        # OGG/Opus (hermes TTS generates .ogg files)
        if (
            content_type.startswith("audio/ogg")
            or url_lower.endswith(".ogg")
            or url_lower.endswith(".opus")
            or audio_bytes[:4] == b"OggS"
        ):
            return self._decode_with_pydub(audio_bytes, "ogg", sample_rate)

        # MP3
        if (
            content_type.startswith("audio/mpeg")
            or url_lower.endswith(".mp3")
            or audio_bytes[:3] in (b"ID3", b"\xff\xfb", b"\xff\xf3")
        ):
            return self._decode_with_pydub(audio_bytes, "mp3", sample_rate)

        # Fallback: try pydub auto-detect, then raw PCM
        result = self._decode_with_pydub(audio_bytes, None, sample_rate)
        if len(result) > 0:
            return result
        return np.frombuffer(audio_bytes, dtype=np.int16)

    @staticmethod
    def _decode_wav(data: bytes) -> np.ndarray:
        """Decode WAV bytes to numpy int16 array."""
        buf = io.BytesIO(data)
        with wave.open(buf, "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            return np.frombuffer(frames, dtype=np.int16)

    @staticmethod
    def _decode_with_pydub(data: bytes, fmt: str | None, sample_rate: int) -> np.ndarray:
        """Decode audio bytes to numpy int16 array using pydub.

        Args:
            data: Raw audio bytes
            fmt: Format hint ("ogg", "mp3", etc.) or None for auto-detect
            sample_rate: Target sample rate for output
        """
        try:
            from pydub import AudioSegment

            buf = io.BytesIO(data)
            if fmt == "ogg":
                seg = AudioSegment.from_ogg(buf)
            elif fmt == "mp3":
                seg = AudioSegment.from_mp3(buf)
            elif fmt:
                seg = AudioSegment.from_file(buf, format=fmt)
            else:
                seg = AudioSegment.from_file(buf)
            seg = seg.set_channels(1).set_frame_rate(sample_rate).set_sample_width(2)
            return np.frombuffer(seg.raw_data, dtype=np.int16)
        except ImportError:
            logger.warning("pydub not installed — cannot decode %s audio", fmt or "unknown")
            return np.array([], dtype=np.int16)
        except Exception as e:
            logger.warning("Failed to decode %s audio: %s", fmt or "unknown", e)
            return np.array([], dtype=np.int16)
