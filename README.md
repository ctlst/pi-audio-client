# Pi Audio Client

Push-to-talk audio thin client for Raspberry Pi Zero W. Connects to [hermes-agent](https://github.com/ctlst/hermes-agent) running on a Mac/server for STT, LLM inference, and TTS — the Pi just handles GPIO, audio I/O, and LED feedback.

## Architecture

```
Pi Zero W (10.1.8.63)                    Mac (100.96.134.76)
┌──────────────────────┐                ┌─────────────────────────┐
│ USB Mic → WAV ───────── POST /pi/audio ──→ hermes gateway       │
│                      │                │   ├─ Whisper STT         │
│ GPIO Buttons (PTT)   │                │   ├─ LLM (Claude/etc)   │
│ GPIO LEDs (status)   │                │   └─ Edge TTS            │
│                      │                │                         │
│ Speaker ← WAV ──────── GET /pi/audio/ ──← JSON {text, audio_url}│
└──────────────────────┘                └─────────────────────────┘
```

The Pi is a **platform adapter** in the hermes gateway — like Telegram or Discord — so it gets full session management, conversation logging, and the existing tool pipeline for free.

## Hardware

- Raspberry Pi Zero W
- USB audio device (mic + speaker — e.g., EarPods with USB adapter)
- 2x LEDs (green for idle, red for listening/processing)
- 2x momentary push buttons (PTT and cancel)
- Resistors for LEDs (330-6.8k ohm depending on LEDs)

### GPIO Pinout

| Function       | GPIO | Physical Pin |
|---------------|------|-------------|
| Green LED      | 6    | 31          |
| Red LED        | 13   | 33          |
| PTT Button     | 25   | 22          |
| Cancel Button  | 26   | 37          |

Buttons need external 10k ohm pull-up resistors to 3.3V to avoid noise on breadboard/long wire setups. See [docs/hardware.md](docs/hardware.md) for full wiring details.

## Setup

### Mac/Server Side (hermes-agent)

1. Add to `~/.hermes/.env`:
   ```
   PI_ENABLED=true
   # PI_API_KEY=optional-secret    # if you want auth
   # PI_HTTP_PORT=8099             # default
   ```

2. Restart the gateway:
   ```bash
   hermes gateway restart
   ```

3. Verify:
   ```bash
   curl http://localhost:8099/pi/health
   # {"status": "ok", "platform": "pi"}
   ```

### Pi Side

1. Clone this repo:
   ```bash
   git clone https://github.com/ctlst/pi-audio-client.git
   cd pi-audio-client
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   sudo apt-get install -y ffmpeg
   ```

3. Copy and edit config:
   ```bash
   cp config.yaml.example config.yaml
   nano config.yaml
   ```
   Set `server.url` to your Mac's IP and port (e.g., `http://100.96.134.76:8099`).

4. Test connectivity:
   ```bash
   curl http://100.96.134.76:8099/pi/health
   ```

5. Run:
   ```bash
   cd ~/pi-audio-client
   python -m src.main
   ```

## Usage

- **Hold PTT** — red LED solid, recording. Release to send. You can send multiple messages without waiting for responses.
- **Tap PTT** — plays the next queued response. Green LED blinks when new messages are waiting.
- **Tap Cancel** — stops current audio playback.
- **Double-tap Cancel** — replays the last message.
- **Idle** — solid green LED (no messages waiting).

Responses arrive asynchronously (10-30s). Green LED blinks when one or more responses are queued. Tap PTT to play them in order. See [docs/interaction-design.md](docs/interaction-design.md) for the full interaction model.

## Configuration

See `config.yaml.example` for all options:

```yaml
server:
  url: "http://100.96.134.76:8099"  # hermes gateway address
  api_key: ""                        # optional auth key
  device_id: "pi-audio-1"           # session identifier

audio:
  sample_rate: 48000                 # must match your USB audio device
  chunk_size: 4096

gpio:
  led_idle: 6                        # green LED pin
  led_listening: 13                  # red LED pin
  button_ptt: 25                     # push-to-talk pin
  button_cancel: 26                  # cancel pin
```

## Session Logging

All Pi conversations are logged in hermes:

```bash
hermes sessions list --source pi
hermes sessions export out.jsonl --source pi
```

## Troubleshooting

- **PulseAudio conflicts**: PulseAudio must be disabled — it fights with ALSA for the USB audio device. Run `systemctl --user disable pulseaudio.socket pulseaudio.service && systemctl --user stop pulseaudio.socket pulseaudio.service`. Verify with `pactl info` (should fail).
- **No audio**: Check `arecord -l` and `aplay -l` for USB device. Ensure `sample_rate` matches device (run `python3 -c "import pyaudio; pa=pyaudio.PyAudio(); print(pa.get_device_info_by_index(0))"` to check).
- **Health check fails**: Verify Mac IP, port 8099 open, `PI_ENABLED=true` in `~/.hermes/.env`, gateway restarted.
- **LEDs not lighting**: Check GPIO pins match wiring, test with `python3 -c "from gpiozero import LED; LED(6).on()"`.
- **Slow audio playback**: The gateway converts TTS to WAV server-side. If still slow, check network latency.

## License

MIT
