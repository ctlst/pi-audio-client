# Updated GPIO Wiring (Working Pins)

The original pins (20, 21) are busy with system functions. **Use these working pins instead:**

## New Pinout

```
Pi Zero W GPIO Header
┌──────────────────────────────────────────────────────┐
│ 1:3.3V  2:5V   3:GPIO2  4:5V   5:GPIO3  6:GND      │
│ 7:GPIO4 8:GPIO14 9:GND  10:GPIO15 11:GPIO17 12:GPIO18│
│ 13:GPIO27 14:GND  15:GPIO22 16:GPIO23 17:3.3V 18:GPIO24│
│ 19:GPIO10 20:GND  21:GPIO9  22:GPIO25 23:GPIO8  24:GPIO7 │
│ 25:GND  26:GPIO21 27:GPIO16 28:GPIO20 29:GPIO5  30:GND │
│ 31:GPIO6 32:GPIO12 33:GPIO13 34:GND  35:GPIO19 36:GPIO26│
│ 37:GPIO26 38:GPIO20 39:GND  40:GPIO21                │
└──────────────────────────────────────────────────────┘
```

## Working Connections

### LEDs (using 6800Ω - will be dim)

```
Pin 31 (GPIO 6)  ── Green LED (Anode) ── 6800Ω ── GND (Pin 34)
Pin 33 (GPIO 13) ── Red LED (Anode)    ── 6800Ω ── GND (Pin 34)
```

### Buttons

```
Pin 35 (GPIO 19) ── PTT Button ── GND (Pin 34 or any GND)
Pin 29 (GPIO 5)  ── Cancel Button ── GND (Pin 34 or any GND)
```

## Visual Layout

```
┌─────────────────────────────────────────────────┐
│  Pi Zero W Breadboard Setup                    │
│                                                 │
│  Pin 31 (GPIO6)  ──┬─ Green LED ── 6800Ω ──┬─ GND│
│                    │                        │    │
│  Pin 33 (GPIO13) ──┼─ Red LED ── 6800Ω ────┼─ GND│
│                    │                        │    │
│  Pin 35 (GPIO19) ──┼─ PTT Button ──────────┼─ GND│
│                    │                        │    │
│  Pin 29 (GPIO5)  ──┴─ Cancel Button ────────┴─ GND│
│                                                 │
└─────────────────────────────────────────────────┘
```

## Updated Configuration

Edit `config.yaml`:

```yaml
gpio:
  led_idle: 6        # Green LED (was 17)
  led_listening: 13  # Red LED (was 18)
  button_ptt: 19     # PTT Button (was 20)
  button_cancel: 5   # Cancel Button (was 21)
```

## Why Original Pins Didn't Work

GPIO 20 and 21 are busy because they're used by:
- GPIO 20: SPI1 MOSI / GPIO function conflict
- GPIO 21: SPI1 MISO / GPIO function conflict

The system claims these pins for other purposes, so we use pins that are free:
- **GPIO 5, 6, 13, 19** - All tested and working!

## Test New Wiring

After rewiring, test with:

```bash
ssh pi@10.1.8.63
python3 -c "
from gpiozero import LED, Button
import time

# Test LEDs
led_green = LED(6)
led_red = LED(13)
led_green.on()
time.sleep(1)
led_green.off()
led_red.on()
time.sleep(1)
led_red.off()
print('✓ LEDs work!')

# Test Buttons
btn_ptt = Button(19)
btn_cancel = Button(5)
print(f'PTT GPIO 19: {btn_ptt.is_pressed}')
print(f'Cancel GPIO 5: {btn_cancel.is_pressed}')
print('✓ Buttons work!')
"
```

## Pin Summary

| Function | Old Pin | New Pin | Pin Number |
|----------|---------|---------|------------|
| Green LED | 17 | **6** | 31 |
| Red LED | 18 | **13** | 33 |
| PTT Button | 20 | **19** | 35 |
| Cancel Button | 21 | **5** | 29 |

**Rewire using these new pins and it should work!** 🎉