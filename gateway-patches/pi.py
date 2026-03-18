"""Pi Audio platform adapter.

HTTP server adapter for the Pi Zero W push-to-talk audio client.
Unlike other adapters (which connect to external services), this adapter
runs an aiohttp HTTP server that the Pi POSTs audio to.

Architecture:
    Pi (GPIO + audio) --HTTP POST WAV--> Mac:8099 (this adapter)
                                            |
                                            v
                                        hermes gateway
                                        (Whisper STT -> LLM agent -> Edge TTS)
                                            |
    Pi (plays audio) <--HTTP response--- JSON {text, audio_url}
"""

import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from aiohttp import web

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    cache_audio_from_bytes,
)

logger = logging.getLogger(__name__)


def check_pi_requirements() -> bool:
    """Check if aiohttp is available."""
    try:
        import aiohttp  # noqa: F401
        return True
    except ImportError:
        return False


class PiAdapter(BasePlatformAdapter):
    """HTTP server adapter for Pi audio clients.

    Key difference from other adapters: Pi is request/response (HTTP POST ->
    wait for agent -> return response), not fire-and-forget.  We override
    handle_message() to process inline so the HTTP handler can await the
    response.  An asyncio.Future keyed by request_id lets send() resolve
    the future, while the HTTP handler awaits it.
    """

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.PI)
        self._port = int(config.extra.get("http_port", 8099))
        self._api_key = config.api_key
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

        # request_id -> Future[str] — send() resolves, HTTP handler awaits
        self._response_futures: Dict[str, asyncio.Future] = {}

    # ------------------------------------------------------------------
    # BasePlatformAdapter interface
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """Start the HTTP server."""
        self._app = web.Application(client_max_size=10 * 1024 * 1024)  # 10MB
        self._app.router.add_post("/pi/audio", self._handle_audio)
        self._app.router.add_get("/pi/audio/{filename}", self._handle_audio_download)
        self._app.router.add_get("/pi/health", self._handle_health)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await self._site.start()

        self._running = True
        logger.info("[Pi] HTTP server listening on port %d", self._port)
        return True

    async def disconnect(self) -> None:
        """Stop the HTTP server."""
        self._running = False
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        logger.info("[Pi] HTTP server stopped")

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Resolve a pending response future with the agent's reply.

        The gateway calls this after the agent finishes.  We extract any
        MEDIA: tags (TTS audio files), build the JSON payload, and
        resolve the future so the HTTP handler can return it to the Pi.
        """
        metadata = metadata or {}
        request_id = metadata.get("request_id", "")

        future = self._response_futures.get(request_id)
        if not future or future.done():
            logger.warning("[Pi] No pending future for request_id=%s", request_id)
            return SendResult(success=False, error="No pending request")

        # Extract MEDIA tags to find TTS audio path
        media_files, clean_text = self.extract_media(content)

        audio_url = None
        if media_files:
            media_path = media_files[0][0]  # first file
            filename = Path(media_path).name
            audio_url = f"/pi/audio/{filename}"

        # Fallback: if agent didn't call TTS, generate it here
        if not audio_url and clean_text.strip():
            try:
                tts_path = await self._generate_tts_fallback(clean_text)
                if tts_path:
                    filename = Path(tts_path).name
                    audio_url = f"/pi/audio/{filename}"
                    logger.info("[Pi] Generated fallback TTS: %s", filename)
            except Exception as e:
                logger.warning("[Pi] Fallback TTS failed: %s", e)

        future.set_result({"text": clean_text, "audio_url": audio_url})
        return SendResult(success=True, message_id=request_id)

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {"name": f"pi-{chat_id}", "type": "dm"}

    async def _generate_tts_fallback(self, text: str) -> Optional[str]:
        """Generate TTS audio when the agent didn't do it."""
        import edge_tts
        from hermes_cli.config import get_hermes_home
        import time as _time

        cache_dir = get_hermes_home() / "audio_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        ts = _time.strftime("%Y%m%d_%H%M%S")
        out_path = str(cache_dir / f"tts_{ts}.mp3")

        communicate = edge_tts.Communicate(text, "en-US-AriaNeural")
        await communicate.save(out_path)

        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path
        return None

    # ------------------------------------------------------------------
    # Override handle_message to process inline (not background task)
    # ------------------------------------------------------------------

    async def handle_message(self, event: MessageEvent) -> None:
        """Process message inline so the HTTP handler can await the response.

        Instead of spawning a background task (base class default), we call
        the message handler directly and let send() resolve the future.
        """
        if not self._message_handler:
            return

        request_id = (event.raw_message or {}).get("request_id", "")

        try:
            response = await self._message_handler(event)
            if response:
                logger.info("[Pi] Agent response (first 500 chars): %s", response[:500])
                # The handler returns the full response text.
                # Route it through send() which resolves the future.
                await self.send(
                    chat_id=event.source.chat_id,
                    content=response,
                    metadata={"request_id": request_id},
                )
            else:
                # No response — resolve with empty
                future = self._response_futures.get(request_id)
                if future and not future.done():
                    future.set_result({"text": "", "audio_url": None})
        except Exception as e:
            logger.error("[Pi] Error handling message: %s", e, exc_info=True)
            future = self._response_futures.get(request_id)
            if future and not future.done():
                future.set_result({"text": f"Error: {e}", "audio_url": None})

    # ------------------------------------------------------------------
    # HTTP handlers
    # ------------------------------------------------------------------

    async def _handle_audio(self, request: web.Request) -> web.Response:
        """Handle POST /pi/audio — receive WAV, process, return JSON."""
        # Auth check
        if self._api_key:
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {self._api_key}":
                return web.json_response({"error": "Unauthorized"}, status=401)

        # Read WAV body
        wav_data = await request.read()
        if not wav_data:
            return web.json_response({"error": "Empty body"}, status=400)

        device_id = request.headers.get("X-Device-ID", "unknown")
        request_id = uuid.uuid4().hex[:12]

        # Cache the audio file so the STT tool can read it
        audio_path = cache_audio_from_bytes(wav_data, ext=".wav")

        # Create a Future that send() will resolve
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._response_futures[request_id] = future

        # Build message event
        source = self.build_source(
            chat_id=device_id,
            chat_name=f"Pi {device_id}",
            chat_type="dm",
            user_id=device_id,
            user_name=device_id,
        )

        event = MessageEvent(
            text=f"[Voice message from Pi device — audio file: {audio_path}]",
            message_type=MessageType.VOICE,
            source=source,
            raw_message={"request_id": request_id, "audio_path": audio_path},
            message_id=request_id,
            media_urls=[audio_path],
            media_types=["audio/wav"],
        )

        # Process inline (our overridden handle_message)
        await self.handle_message(event)

        # Wait for the response (send() resolves the future)
        try:
            result = await asyncio.wait_for(future, timeout=120)
        except asyncio.TimeoutError:
            result = {"text": "Request timed out", "audio_url": None}
        finally:
            self._response_futures.pop(request_id, None)

        return web.json_response(result)

    async def _handle_audio_download(self, request: web.Request) -> web.Response:
        """Handle GET /pi/audio/{filename} — serve TTS audio as WAV.

        The Pi Zero is too slow to decode OGG/MP3 with ffmpeg, so we
        convert to WAV on the Mac (fast) and send raw PCM the Pi can
        play directly.
        """
        filename = request.match_info["filename"]

        from hermes_cli.config import get_hermes_home

        search_dirs = [
            get_hermes_home() / "audio_cache",
            get_hermes_home() / "tts_cache",
            Path("/tmp"),
        ]

        filepath = None
        for search_dir in search_dirs:
            candidate = search_dir / filename
            # Prevent path traversal
            if not candidate.resolve().is_relative_to(search_dir.resolve()):
                continue
            if candidate.exists():
                filepath = candidate
                break

        if not filepath:
            return web.json_response({"error": "Not found"}, status=404)

        # If already WAV, serve directly
        if filepath.suffix.lower() == ".wav":
            return web.FileResponse(filepath, headers={"Content-Type": "audio/wav"})

        # Convert OGG/MP3/etc to WAV on the Mac (fast) so the Pi
        # doesn't have to spend 30+ seconds decoding on its ARM CPU
        try:
            wav_path = filepath.with_suffix(".wav")
            if not wav_path.exists():
                import subprocess
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(filepath),
                     "-ar", "48000", "-ac", "1", "-sample_fmt", "s16",
                     str(wav_path)],
                    capture_output=True, timeout=10,
                )
            if wav_path.exists():
                return web.FileResponse(wav_path, headers={"Content-Type": "audio/wav"})
        except Exception as e:
            logger.warning("[Pi] WAV conversion failed: %s", e)

        # Fallback: serve original file
        return web.FileResponse(filepath)

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handle GET /pi/health."""
        return web.json_response({"status": "ok", "platform": "pi"})
