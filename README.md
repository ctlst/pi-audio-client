# Pi Audio Client

Push-to-talk audio thin client for Raspberry Pi Zero W. Connects to [hermes-agent](https://github.com/NousResearch/hermes-agent) running on a Mac/server for STT, LLM inference, and TTS — the Pi just handles GPIO, audio I/O, and LED feedback.

## Architecture

```
Pi Zero W                                Mac / Server
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
- USB audio device (mic + speaker — e.g., EarPods with USB-C adapter)
- 2x LEDs (green for idle, red for listening/processing)
- 2x momentary push buttons (PTT and cancel)
- Resistors for LEDs (330-6.8k ohm depending on LEDs)

### GPIO Pinout

| Function       | GPIO | Physical Pin |
|---------------|------|-------------|
| Green LED      | 6    | 31          |
| Red LED        | 13   | 33          |
| PTT Button     | 19   | 35          |
| Cancel Button  | 5    | 29          |

Buttons use internal pull-ups. External 10k pull-up resistors to 3.3V are recommended for long wire runs or breadboard setups to avoid noise.

See [docs/hardware.md](docs/hardware.md) for full wiring details.

## Setup

### 1. Mac/Server Side (hermes-agent)

The Pi platform adapter is not included in upstream hermes-agent. You need to apply the patches from `gateway-patches/` in this repo.

```bash
cd ~/.hermes/hermes-agent

# Copy the Pi platform adapter
cp <path-to-pi-audio-client>/gateway-patches/pi.py gateway/platforms/pi.py

# Apply config and run patches
git apply <path-to-pi-audio-client>/gateway-patches/config.patch
git apply <path-to-pi-audio-client>/gateway-patches/run.patch
```

Add to `~/.hermes/.env`:

```
PI_ENABLED=true
# PI_API_KEY=optional-secret    # if you want auth
# PI_HTTP_PORT=8099             # default
```

Restart the gateway:

```bash
hermes gateway restart
```

Verify:

```bash
curl http://localhost:8099/pi/health
# {"status": "ok", "platform": "pi"}
```

See [gateway-patches/README.md](gateway-patches/README.md) for details on what the patches do and how to re-apply after hermes-agent updates.

### 2. Pi Side

Tested on Raspbian Bookworm (Debian 12) with Python 3.11. Other Debian-based distros should work.

```bash
# Install system dependencies (portaudio is required for pyaudio)
sudo apt-get update
sudo apt-get install -y python3-pip python3-dev portaudio19-dev ffmpeg

# Disable PulseAudio — it conflicts with ALSA for USB audio
systemctl --user disable pulseaudio.socket pulseaudio.service
systemctl --user stop pulseaudio.socket pulseaudio.service

# Clone
git clone https://github.com/ctlst/pi-audio-client.git
cd pi-audio-client

# Install Python dependencies
# On Bookworm, use --break-system-packages or create a venv
pip install -r requirements.txt --break-system-packages
```

Configure your audio device and server:

```bash
cp config.yaml.example config.yaml
nano config.yaml
```

Find your USB audio device name and supported sample rate:

```bash
# List audio devices
arecord -l
aplay -l

# Check device capabilities (replace hw:0,0 with your device)
python3 -c "import pyaudio; pa=pyaudio.PyAudio(); print(pa.get_device_info_by_index(0))"
```

Set `server.url` to your Mac/server IP and port (e.g., `http://192.168.1.100:8099`), or set the `PI_SERVER_URL` environment variable. Set `audio.input_device` and `audio.output_device` to match your USB audio device name (e.g., `"EarPods"`). Set `audio.sample_rate` to match your device's native rate (commonly 48000 for USB audio).

Test connectivity:

```bash
curl http://<your-mac-ip>:8099/pi/health
# {"status": "ok", "platform": "pi"}
```

### 3. Run

```bash
python3 -m src.main
```

Or install as a systemd service for auto-start on boot:

```bash
sudo cp config/pi-audio-client.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pi-audio-client
sudo systemctl start pi-audio-client

# Check status
sudo systemctl status pi-audio-client
sudo journalctl -u pi-audio-client -f
```

## Usage

### Buttons

| Action | What happens |
|--------|-------------|
| **Hold PTT** (>0.5s) | Red LED on, recording. Release to send to hermes. |
| **Tap PTT** (<0.5s) | Plays the next queued response. |
| **Press Cancel** (while playing) | Stops current audio playback. |
| **Press Cancel** (while idle) | Replays the last response. |

### LED States

| LED | Meaning |
|-----|---------|
| Solid green | Idle, ready |
| Solid red | Recording (PTT held) |
| Blinking red | Processing (waiting for hermes response) |
| Slow blinking green | Message waiting (tap PTT to play) |
| Fast blinking green | Playing audio |
| Fast blinking red | Error |

### Flow

1. Hold PTT and speak. Red LED turns on while recording (max 30 seconds).
2. Release PTT. Red LED blinks while hermes processes (STT, LLM, TTS).
3. When a response arrives, green LED blinks slowly.
4. Tap PTT to play the response.
5. Press cancel to replay, or hold PTT to send another message.

Responses arrive asynchronously. You can send multiple messages before playing any responses — they queue up in order.

## Configuration

See `config.yaml.example` for all options:

```yaml
server:
  url: "http://localhost:8099"       # hermes gateway address (or PI_SERVER_URL env var)
  api_key: ""                        # optional auth key (or PI_API_KEY env var)
  device_id: "pi-audio-1"           # session identifier

audio:
  input_device: null                 # USB mic name (null = default)
  output_device: null                # speaker name (null = default)
  sample_rate: 48000                 # must match your USB audio device
  chunk_size: 4096

gpio:
  led_idle: 6                        # green LED pin
  led_listening: 13                  # red LED pin
  button_ptt: 19                     # push-to-talk pin
  button_cancel: 5                   # cancel pin
```

Environment variables `PI_SERVER_URL`, `PI_API_KEY`, and `PI_DEVICE_ID` override config.yaml values.

## Session Logging

All Pi conversations are logged in hermes:

```bash
hermes sessions list --source pi
hermes sessions export out.jsonl --source pi
```

## Troubleshooting

- **PulseAudio conflicts**: PulseAudio must be disabled — it fights with ALSA for the USB audio device. Run `systemctl --user disable pulseaudio.socket pulseaudio.service && systemctl --user stop pulseaudio.socket pulseaudio.service`. Verify with `pactl info` (should fail).
- **No audio devices**: Check `arecord -l` and `aplay -l` for USB device. Ensure `sample_rate` in config matches your device capabilities.
- **Health check fails**: Verify Mac IP, port 8099 open, `PI_ENABLED=true` in `~/.hermes/.env`, gateway restarted.
- **LEDs not lighting**: Check GPIO pins match wiring, test with `python3 -c "from gpiozero import LED; LED(6).on()"`.
- **Instant green on PTT release / no audio**: The Pi Zero W USB controller (`dwc2`) degrades over time. Reboot the Pi.
- **413 Request Entity Too Large**: Recording exceeded the gateway's max request size. The Pi caps recordings at 30s, and the gateway patch sets a 10MB limit.
- **Transcription errors**: Check that `stt.provider` is set to `local` and `stt.local.model` is a valid faster-whisper model (e.g., `base`, `small`, `medium`) in `~/.hermes/config.yaml`.

## Known Issues

- **Pi Zero W USB instability**: The `dwc2` USB host controller produces `dwc2_hc_halt` kernel errors over time, eventually causing audio I/O to hang. Only a full reboot fixes it. Consider a powered USB hub or I2S audio hat for better reliability.
- **Service restarts are not enough**: After deploying code changes, always reboot the Pi (`sudo reboot`) rather than just restarting the service. The USB audio streams don't recover cleanly from a service restart.

## License

MIT
