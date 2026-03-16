# Quick Test Guide for Pi Audio Client

## Step 1: Wire Everything Up

### LED Wiring (using 6800Ω resistors - will be dim)
```
GPIO 17 (Pin 11) ── Green LED ── 6800Ω ── GND
GPIO 18 (Pin 12) ── Red LED    ── 6800Ω ── GND
```

### Button Wiring
```
GPIO 20 (Pin 38) ── PTT Button ── GND
GPIO 21 (Pin 40) ── Cancel Button ── GND
```

### USB Headphones
- Plug into USB port on Pi
- Should be auto-detected

## Step 2: Connect to Pi

```bash
# SSH into Pi
ssh pi@10.1.8.63

# Navigate to project
cd /home/pi/pi-audio-client

# Run quick test
python tests/test_quick.py
```

## Step 3: Expected Results

### LED Test
- Green LED should turn on (GPIO 17)
- Red LED should turn on (GPIO 18)
- LEDs will be **dim** with 6800Ω resistors (expected!)
- Both should light up when tested

### Button Test
- Press PTT button → Should detect press
- Press Cancel button → Should detect press
- Both should work

### Audio Test
- USB headphones should be detected
- Should show input/output device names

### hermes-agent Test
- Should connect to Mac at 100.96.134.76
- If hermes-agent is running, should see response
- If not running, will show connection error (expected)

## Step 4: Troubleshooting

### LEDs not lighting
- **Expected with 6800Ω resistors** - They'll be very dim
- Check: Long leg of LED to GPIO, short leg to resistor
- Try: Use flashlight to see if LEDs are barely lit

### Buttons not detected
- Check: Both legs of button connected (one to GPIO, one to GND)
- Check: Button is momentary (not latching)
- Check: Pull-up enabled in code (it is!)

### Audio not working
- Check: USB headphones plugged in
- Check: Audio device selected in config
- Try: `arecord -l` and `aplay -l` to list devices

### hermes-agent not reachable
- Check: Mac is on (100.96.134.76)
- Check: hermes-agent is running on Mac
- Check: Firewall not blocking port 8081
- Try: `curl http://100.96.134.76:8081/v1/health` on Mac

## Step 5: Next Steps

1. ✅ Test GPIO (LEDs and buttons)
2. ✅ Test audio (headphones)
3. ⏳ Test hermes-agent connection
4. ⏳ Run full main.py
5. ⏳ Full PTT test!

## Test Commands

```bash
# Quick test
python tests/test_quick.py

# Test just GPIO
python -c "from gpiozero import LED, Button; l=LED(17); l.on(); input('Press Enter to turn off'); l.off()"

# Test audio recording
arecord -f cd -d 5 test.wav
aplay test.wav

# Run main client
python src/main.py
```

Enjoy testing! 🎉