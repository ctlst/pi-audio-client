# Ready to Test - Pi Audio Client

## ✅ All Components Working

| Component | GPIO Pin | Status |
|-----------|----------|--------|
| Green LED (Idle) | GPIO 17 (Pin 11) | ✅ Tested |
| Red LED (Listening) | GPIO 18 (Pin 12) | ✅ Tested |
| PTT Button | GPIO 25 (Pin 22) | ✅ Tested (18 presses) |
| Cancel Button | GPIO 26 (Pin 37) | ✅ Tested (8 presses) |
| USB Audio | USB Port | ✅ EarPods detected |

## 📡 Server Connection

**Server URL:** `http://100.107.234.90:8081/v1`

**Status:** ✅ RTX 3090 server is reachable and responding (HTTP 200)

## 🎯 Final Configuration

```yaml
server:
  url: "http://100.107.234.90:8081/v1"
  api_key: ""

audio:
  input_device: null  # Uses default USB audio
  output_device: null  # Uses default USB audio
  sample_rate: 16000
  chunk_size: 1024

gpio:
  led_idle: 17
  led_listening: 18
  button_ptt: 25
  button_cancel: 26

state:
  timeout_idle: 30
  timeout_recording: 30
  timeout_speaking: 60
```

## 🚀 How to Test

### 1. Wire Everything Up
```
Pin 11  (GPIO 17) ── Green LED ── 220Ω ── GND
Pin 12  (GPIO 18) ── Red LED    ── 220Ω ── GND
Pin 22  (GPIO 25) ── PTT Button ── GND
Pin 37  (GPIO 26) ── Cancel Button ── GND
USB   (USB-A)     ── Headphones (Mic + Speaker)
```

### 2. Start the Client
```bash
cd /home/pi/pi-audio-client
python src/main.py
```

### 3. Test the Flow
1. Press **PTT Button** → Red LED lights up
2. Speak into USB microphone
3. Release PTT → Processing (LEDs blink)
4. AI response plays through headphones
5. Green LED lights up (idle)

## 📋 Architecture

```
┌─────────────────────┐          HTTP          ┌─────────────────────┐
│   Pi Zero W         │ ───────────────────→   │  RTX 3090 Server    │
│   (Thin Client)     │                        │  (100.107.234.90)   │
│   - USB Mic         │                        │  Qwen 3.5 35B       │
│   - Speaker         │                        │  llama.cpp / Ollama │
│   - PTT + LEDs      │                        │  - LLM inference    │
│                     │                        │  - TTS generation   │
└─────────────────────┘                        └─────────────────────┘
```

## 🔧 Troubleshooting

**LEDs not lighting?**
- Check resistor connections (220Ω, not 6800Ω)
- Verify GPIO pins (17, 18)
- Test with: `python3 -c "from gpiozero import LED; LED(17).on(); input('Press Enter'); LED(17).off()"`

**Buttons not detected?**
- Check GPIO pins (25, 26)
- Verify pull-up resistors (internal, no external needed)
- Test with: `sudo python3 final_button_test.py`

**Audio not working?**
- Verify USB headphones plugged in
- Check with: `sudo arecord -l` and `sudo aplay -l`
- Test recording: `sudo arecord -D hw:1,0 -f cd -d 3 test.wav`

**Server connection failing?**
- Verify RTX 3090 server is running
- Check Tailscale connection: `tailscale status`
- Test connection: `curl http://100.107.234.90:8081/v1/health`

## ✅ You're Ready!

All components are tested and working. Just:
1. Wire up the components
2. Install the client on Pi
3. Run `python src/main.py`
4. Press PTT and speak!

Good luck with your project! 🎉🚀