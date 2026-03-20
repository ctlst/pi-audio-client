# Hermes Gateway Patches for Pi Platform

These files add Pi Audio Client support to [hermes-agent](https://github.com/NousResearch/hermes-agent). They are not part of the upstream repo and must be applied manually.

## Files

- `pi.py` — Full Pi platform adapter (copy to `gateway/platforms/`)
- `config.patch` — Adds `PI` to Platform enum + env var loading
- `run.patch` — Adds Pi adapter creation + auth bypass

## Setup (after fresh clone or git pull of hermes-agent)

```bash
# From your hermes-agent directory (e.g. ~/.hermes/hermes-agent)

# 1. Copy the Pi platform adapter
cp <path-to-pi-audio-client>/gateway-patches/pi.py gateway/platforms/pi.py

# 2. Apply the config and run patches
git apply <path-to-pi-audio-client>/gateway-patches/config.patch
git apply <path-to-pi-audio-client>/gateway-patches/run.patch

# 3. Add to ~/.hermes/.env
#    PI_ENABLED=true
#    PI_API_KEY=       (optional)
#    PI_HTTP_PORT=8099 (optional, this is the default)
#    PI_DEBUG_LOG_TRANSCRIPTS=false (optional)

# 4. Restart the gateway
hermes gateway restart
```

## What the patches do

### config.patch (gateway/config.py)
- Adds `PI = "pi"` to the `Platform` enum
- Adds env var loading for `PI_ENABLED`, `PI_API_KEY`, `PI_HTTP_PORT`, `PI_DEBUG_LOG_TRANSCRIPTS`

### run.patch (gateway/run.py)
- Adds Pi adapter creation in `_create_adapter()` (imports `PiAdapter` from `gateway.platforms.pi`)
- Auto-authorizes Pi platform in `_is_user_authorized()` (same as HomeAssistant — the Pi authenticates via API key, not user allowlists)

### pi.py (gateway/platforms/pi.py)
- HTTP server adapter using aiohttp (listens on port 8099)
- Reads auth and port from `extra["api_key"]` and `extra["port"]`, matching `config.patch`
- Endpoints: `POST /pi/audio`, `GET /pi/audio/{filename}`, `GET /pi/health`
- Fallback TTS: if the LLM agent doesn't call `text_to_speech`, the gateway generates Edge TTS directly so the Pi always gets audio back
- 10MB max request size (supports up to ~30s recordings at 48kHz)

## After a hermes-agent git pull

Patches to `config.py` and `run.py` will be overwritten. Re-apply:

```bash
cp <path>/gateway-patches/pi.py gateway/platforms/pi.py  # usually survives (untracked)
git apply <path>/gateway-patches/config.patch             # may need manual fix if upstream changed
git apply <path>/gateway-patches/run.patch                # may need manual fix if upstream changed
hermes gateway restart
```

If patches fail to apply cleanly, the changes are small enough to apply by hand — see the patch files for the exact lines.
