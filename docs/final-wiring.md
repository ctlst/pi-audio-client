# Final Working GPIO Pin Configuration

## ✅ CONFIRMED WORKING PINS

### LEDs
```
Green LED (Idle):    GPIO 17 (Pin 11) ── LED ── 220Ω ── GND
Red LED (Listening): GPIO 18 (Pin 12) ── LED ── 220Ω ── GND
```

### Buttons
```
PTT Button:    GPIO 25 (Pin 22) ── Button ── GND
Cancel Button: GPIO 26 (Pin 37) ── Button ── GND
```

## Pin Reference (Pi Zero W Header)

```
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

## Complete Wiring Diagram

```
┌─────────────────────────────────────────────────┐
│  Pi Zero W Breadboard Setup                    │
│                                                 │
│  Pin 11 (GPIO17) ──┬─ Green LED ── 220Ω ──┬─ GND│
│                    │                        │    │
│  Pin 12 (GPIO18) ──┼─ Red LED ── 220Ω ────┼─ GND│
│                    │                        │    │
│  Pin 22 (GPIO25) ──┼─ PTT Button ──────────┼─ GND│
│                    │                        │    │
│  Pin 37 (GPIO26) ──┴─ Cancel Button ────────┴─ GND│
│                                                 │
│  USB Port: ────────────────────────────────────┤
│              Headphones (Mic + Speaker)       │
└─────────────────────────────────────────────────┘
```

## Summary

| Component | GPIO Pin | Header Pin | Status |
|-----------|----------|------------|--------|
| Green LED | GPIO 17 | Pin 11 | ✅ Tested & Working |
| Red LED | GPIO 18 | Pin 12 | ✅ Tested & Working |
| PTT Button | GPIO 25 | Pin 22 | ✅ Tested (18 presses) |
| Cancel Button | GPIO 26 | Pin 37 | ✅ Tested (8 presses) |
| USB Audio | - | USB Port | ✅ EarPods detected |

## Configuration (config.yaml)

```yaml
gpio:
  led_idle: 17
  led_listening: 18
  button_ptt: 25
  button_cancel: 26
```

All components are working! 🎉