# Pi Audio Client Code Review

## Executive Summary

This project has a sensible high-level split for a Raspberry Pi thin client:

- `src/main.py` coordinates GPIO, audio capture/playback, and Hermes communication.
- `src/audio/` isolates PyAudio input/output.
- `src/gpio/` wraps button and LED handling.
- `src/client/hermes_client.py` handles HTTP transport to the Hermes gateway.
- `src/config/settings.py` provides YAML and environment-based configuration.
- `gateway-patches/` contains the actual server-side Pi platform integration for Hermes.

The architecture is intentionally thin on the Pi and pushes STT/LLM/TTS to the server, which is the right direction for Pi Zero hardware. The main risks are not architectural complexity; they are correctness gaps, stale tests, configuration drift, and a few server-side patch bugs that can break auth and port configuration.

Overall assessment: good prototype structure, but not yet production-ready without fixing the high-severity issues below.

## High-Severity Findings

### 1. Hermes gateway patch has mismatched config keys for API key and port

The Pi gateway patch appears internally inconsistent:

- `gateway-patches/pi.py:59-60` reads `config.extra["http_port"]` and `config.api_key`
- `gateway-patches/config.patch:25-30` writes `extra["api_key"]` and `extra["port"]`

Impact:

- `PI_HTTP_PORT` may be ignored because the adapter expects `http_port`, not `port`.
- `PI_API_KEY` may be ignored because the adapter reads `config.api_key`, not `extra["api_key"]`.
- README instructions around optional auth and custom port can therefore fail even if the user follows them correctly.

Recommendation:

- Make the patch consistent with Hermes `PlatformConfig`.
- Prefer setting `config.platforms[Platform.PI].api_key = pi_api_key` and `extra["http_port"] = int(pi_port)`, or change `pi.py` to read the keys that `config.patch` actually sets.

### 2. Test suite is effectively broken and does not validate current behavior

Two separate issues make the current test story unreliable:

- `tests/test_quick.py:1-156` is an executable hardware smoke script, not a pytest test module. It runs at import time and calls `sys.exit(1)`, which breaks pytest collection. Running `pytest -q` in this repo currently fails during collection for that reason.
- `tests/test_ptt_flow.py:68-200` is stale relative to the implementation:
  - It calls `client._on_ptt_release()` but the real method is `_on_ptt_released()` in `src/main.py:156`.
  - It expects `_on_ptt_pressed()` to start recording immediately, but the real code only records after the hold threshold in `src/main.py:120-135`.

Impact:

- CI cannot be trusted.
- Regressions in core PTT behavior, queueing, and playback are not meaningfully covered.
- The tests currently give false confidence about the behavior they claim to verify.

Recommendation:

- Move `tests/test_quick.py` out of `tests/` or rename it to a non-pytest filename.
- Rewrite `tests/test_ptt_flow.py` against the actual press/hold/release flow.
- Add tests for queue behavior, cancel behavior, config overrides, and error paths.

### 3. Required runtime dependencies are incomplete/inconsistent

The project uses `numpy` directly in runtime code:

- `src/main.py:23`
- `src/audio/input.py:4`
- `src/audio/output.py:4`
- `src/client/hermes_client.py:18`

But `numpy` is only present in `requirements.txt:8`, not `pyproject.toml:21-29`.

The client also references `pydub` in `src/client/hermes_client.py:184-203`, but `pydub` is not listed in either `pyproject.toml` or `requirements.txt`.

At the same time, `sounddevice` and `soundfile` are declared in both manifests:

- `pyproject.toml:27-28`
- `requirements.txt:6-7`

but do not appear to be used anywhere in the codebase.

Impact:

- Installing from package metadata can produce a broken runtime because `numpy` is missing.
- Audio decoding paths may silently degrade because `pydub` is optional but undocumented.
- Dependency surface is larger than necessary.

Recommendation:

- Add `numpy` to `pyproject.toml`.
- Either add `pydub` explicitly or remove the code path and require WAV from the gateway.
- Remove unused dependencies unless they are intentionally planned.

## Medium-Severity Findings

### 4. Whisper/STT configuration is not managed by this project and is only loosely documented

The Pi client does not configure Whisper directly. STT is delegated entirely to Hermes via the gateway:

- described in `README.md:3, 11-13, 224`
- represented in `gateway-patches/pi.py:219-247`

What this repo actually does:

- Sends recorded WAV to `/pi/audio`
- Depends on Hermes to decide how STT runs
- Mentions a faster-whisper configuration in documentation only (`README.md:224`)

Issues:

- There is no local validation that Hermes is configured for the expected STT backend.
- There is no compatibility contract between Pi sample rate/config and server-side transcription expectations.
- The project claims Whisper/faster-whisper usage in docs, but that behavior is outside this repository.

Recommendation:

- Document clearly that Whisper configuration lives in Hermes, not in this client.
- Add a compatibility matrix or a startup warning if Hermes health metadata can expose STT provider/model.
- If STT correctness matters operationally, add a `/pi/health` payload or dedicated capability endpoint that includes active STT backend, model, and max supported request size.

### 5. Configuration management is simple, but it has drift and incomplete semantics

Strengths:

- `src/config/settings.py:53-109` uses typed Pydantic models.
- YAML plus environment overrides is a reasonable fit for this deployment model.

Problems:

- `reload_config()` in `src/config/settings.py:112-116` does not reapply environment overrides, unlike `load_config()`.
- Config is cached globally in `_config` (`src/config/settings.py:89-109`), which makes runtime reconfiguration and tests less predictable.
- `state` configuration exists in `src/config/settings.py:46-50` and `config.yaml.example:20-23`, but none of those values are actually used by `src/main.py`. The code uses hard-coded constants instead:
  - `HOLD_THRESHOLD` in `src/main.py:38`
  - `MAX_RECORDING_SECS` in `src/main.py:40`
- README and example config disagree on recommended audio settings:
  - `config.yaml.example:11-12` uses `16000` / `1024`
  - `README.md:195-196` shows `48000` / `4096`

Impact:

- Operators can change config values that have no runtime effect.
- Reload behavior is inconsistent.
- Audio tuning can drift between docs and actual defaults.

Recommendation:

- Decide which settings are truly configurable and wire them all the way through.
- Reapply env overrides in `reload_config()`.
- Remove dead config fields or consume them in code.
- Keep README and `config.yaml.example` aligned.

### 6. Playback and queue handling are vulnerable to concurrency races

The playback model in `src/main.py` is thread-based and mostly unguarded:

- `_play_next_message()` starts a new playback thread without checking `_playing` (`src/main.py:198-207`)
- `_on_cancel_pressed()` can start a replay thread whenever `_playing` is false (`src/main.py:213-222`)
- `_play_response()` sets `_playing` without a lock (`src/main.py:256-270`)

Potential outcomes:

- Rapid PTT taps can dequeue multiple responses and start overlapping playback threads.
- A cancel/replay press racing with the normal playback path can create duplicate playbacks.
- `_last_audio` and `_playing` are shared mutable state without synchronization.

Recommendation:

- Serialize playback with a dedicated lock or a single playback worker thread.
- Reject or queue play requests while playback is active.
- Treat replay as a message enqueue or explicit state transition instead of spawning ad hoc threads.

### 7. `ButtonController.wait_for_*` reports success even on timeout

In `src/gpio/buttons.py:79-109`, both `wait_for_ptt()` and `wait_for_cancel()` ignore the boolean result from `Event.wait()` and always return `True` unless an exception is raised.

Impact:

- Any caller using these helpers would mis-handle timeouts as successful presses.

Recommendation:

- Return the actual result of `Event.wait(timeout=...)`.

### 8. `ButtonEventHandler` is incomplete / dead code

`src/gpio/buttons.py:120-153` contains a `ButtonEventHandler` that is not used by the rest of the project, and `on_ptt_release()` is a stub (`pass`).

Impact:

- Unused abstractions make the GPIO layer harder to reason about.
- Future contributors may assume this class is part of the live control path when it is not.

Recommendation:

- Remove it or finish integrating it.

### 9. Logging can expose sensitive conversational content

The code logs partial transcripts and responses:

- `src/main.py:183, 206, 236`
- `src/client/hermes_client.py:84`
- `gateway-patches/pi.py:180`

Impact:

- Voice content may end up in journal logs on the Pi and on the gateway host.
- This is a privacy concern, especially if the device is used in shared spaces.

Recommendation:

- Default to metadata-only logs in production.
- Gate transcript logging behind a debug flag.

## Low-Severity Findings

### 10. Packaging layout is unconventional and fragile

The package structure uses `src/` as both source root and import package name:

- entry point `pyproject.toml:39-40` is `src.main:main`
- imports throughout the code are `from src...`

This can work, but it is unusual and easy to mis-handle in packaging, testing, and tooling. The repo also lacks a `package-dir` declaration, which makes the install semantics less obvious than a standard `src/` layout.

Recommendation:

- Either keep `src` as a real package very intentionally and document it, or move to a standard layout such as package `pi_audio_client` under `src/`.

### 11. Python version/tooling expectations are not consistently enforceable

- `pyproject.toml:10` requires Python `>=3.11`
- The current local interpreter available as `python3` is `3.9.6`
- `mypy` is configured (`pyproject.toml:56-58`) but not present in dev dependencies

Impact:

- Developer environments can drift from declared support.
- Static typing expectations are aspirational rather than enforced.

Recommendation:

- Add `mypy` to dev dependencies if strict typing is a real requirement.
- Provide a reproducible dev environment (`.python-version`, `uv`, `poetry`, `tox`, or `nox`).

## Project Structure and Architecture Review

### What is working well

- Thin-client architecture is appropriate for Pi Zero W constraints.
- Server-side conversion of TTS output to WAV in `gateway-patches/pi.py:259-311` is a practical optimization.
- Separation of concerns is clear enough for a small project.
- `client_max_size=10MB` in `gateway-patches/pi.py:74` is a sensible guardrail.

### Architectural weaknesses

- Critical behavior spans two codebases: the Pi client and Hermes patches. This repo documents that dependency, but operational correctness depends heavily on code not version-locked here.
- The runtime model mixes polling, GPIO callbacks, background worker threads, and shared mutable state without a formal state machine.
- Several behaviors are encoded in constants rather than config.

Best-practice recommendation:

- Move the runtime control flow toward an explicit state machine with serialized transitions for `idle`, `recording`, `processing`, `message_waiting`, and `playing`.

## Audio Capture and Streaming Review

### Strengths

- Using WAV upload avoids custom binary framing and keeps the server side simple.
- `AudioInput.read_chunk()` uses `exception_on_overflow=False` (`src/audio/input.py:76`), which is a pragmatic choice on slow hardware.

### Risks

- Device matching is substring-based in both `src/audio/input.py:34-40` and `src/audio/output.py:34-40`; ambiguous device names can select the wrong interface.
- There is no capability validation before opening streams. If the configured sample rate is unsupported, startup fails late and opaquely.
- The client assumes mono 16-bit PCM everywhere. That is fine, but it should be explicit in config validation and docs.
- Playback writes are blocking (`src/audio/output.py:76-80`), which is simple but means slow or broken output can stall a playback thread indefinitely.

Recommendations:

- Validate selected devices and supported sample rates during startup.
- Prefer stable device identifiers if available.
- Surface startup diagnostics that include selected input/output devices and hardware parameters.

## Speech-to-Text / Whisper Review

### Current model

- STT is not implemented on the Pi.
- The effective STT path is: Pi records WAV -> gateway caches WAV -> Hermes message pipeline processes voice event -> Whisper/faster-whisper runs on the server.

### Main concern

This repository does not own Whisper configuration; it only assumes it exists. The only explicit STT guidance is in docs (`README.md:224`), so operational failures will look like "Pi bugs" even when the root cause is server misconfiguration.

Recommendations:

- Expose STT backend/model info in gateway health output.
- Add a setup validation checklist specifically for server-side STT.
- Version the Hermes patch compatibility against specific upstream Hermes commits or releases.

## Dependencies and Requirements Review

### Positive

- The dependency list is still fairly small.

### Issues

- Two dependency manifests are duplicated and already out of sync.
- Some runtime imports are missing from package metadata.
- Some declared packages are unused.
- Gateway patch dependencies (`aiohttp`, `edge_tts`, likely `ffmpeg` on the server) are documented but not managed here.

Recommendations:

- Pick one source of truth for dependencies.
- Separate Pi-client dependencies from gateway-patch dependencies.
- Document system packages per host role: Pi versus Hermes host.

## Security Review

### Positive

- Path traversal protection in `gateway-patches/pi.py:277-281` is good.
- The gateway supports optional bearer-token auth.

### Concerns

- Auth is optional and transport is plain HTTP, so credentials and voice traffic are exposed on untrusted networks.
- Device identity comes entirely from `X-Device-ID` (`gateway-patches/pi.py:216`), which is fine for a trusted LAN but should not be treated as secure identity.
- Logs include conversational content.

Recommendations:

- Treat this as trusted-LAN software unless TLS or a tunnel is added.
- Require API key auth by default for any non-isolated network.
- Reduce content logging.

## Best Practices and Next Steps

Recommended priority order:

1. Fix the Hermes patch key mismatches for API key and port.
2. Repair the test suite so `pytest` can run and accurately reflect current behavior.
3. Reconcile dependency manifests and add missing runtime dependencies.
4. Make configuration authoritative by wiring real settings through the runtime and removing dead ones.
5. Serialize playback/state transitions to eliminate race-prone thread spawning.
6. Clarify server-side Whisper ownership and add health/capability checks.

## Validation Notes

Review methods used:

- Static inspection of the repository structure and core modules.
- Inspection of gateway patch files because STT and HTTP behavior depend on them.
- Test execution attempt with `pytest -q`, which currently fails during collection due to `tests/test_quick.py`.

Environment limitations during review:

- `ruff` was not installed in the current environment.
- `python3` on this machine is `3.9.6`, while the project declares Python `>=3.11`.
- The local environment does not have the project dependencies installed, so this review is based primarily on static analysis plus the observed pytest collection failure.
