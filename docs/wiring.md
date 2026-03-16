# GPIO Wiring Guide for Pi Audio Client

## Pinout Diagram

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

Legend:
  3.3V = 3.3V power
  5V   = 5V power
  GND  = Ground (0V)
  GPIO = General Purpose Input/Output
```

## Component Connections

### LEDs (Green = Idle, Red = Listening)

```
Green LED:
  GPIO17 (Pin 11) ── Anode (Long Leg)
                      Cathode (Short Leg) ── 220Ω Resistor ── GND (Pin 9)

Red LED:
  GPIO18 (Pin 12) ── Anode (Long Leg)
                       Cathode (Short Leg) ── 220Ω Resistor ── GND (Pin 9)
```

### Buttons (PTT = Push-to-Talk, Cancel = Stop)

```
PTT Button:
  GPIO20 (Pin 38) ── One Leg
                       Other Leg ── GND (Pin 39 or any GND)

Cancel Button:
  GPIO21 (Pin 40) ── One Leg
                       Other Leg ── GND (Pin 39 or any GND)
```

## Physical Wiring Layout

```
┌─────────────────────────────────────────────────┐
│  Pi Zero W Breadboard Setup                    │
│                                                 │
│  Pin 11 (GPIO17) ──┬─ Green LED ── 220Ω ──┬─ GND│
│                    │                        │    │
│  Pin 12 (GPIO18) ──┼─ Red LED ── 220Ω ────┼─ GND│
│                    │                        │    │
│  Pin 38 (GPIO20) ──┼─ PTT Button ──────────┼─ GND│
│                    │                        │    │
│  Pin 40 (GPIO21) ──┴─ Cancel Button ────────┴─ GND│
│                                                 │
└─────────────────────────────────────────────────┘
```

## Component Values

| Component | Value | Purpose |
|-----------|-------|---------|
| LED | 5mm standard | Visual indicators |
| Resistor | 220Ω | Current limiting for LEDs |
| Button | Tactile push | Momentary contact |
| Jumper | Male-to-Male | Connections |

## Testing

**Test LEDs:**
```python
from gpiozero import LED
led_green = LED(17)
led_red = LED(18)
led_green.on()  # Should light up
led_red.on()    # Should light up
led_green.off()
led_red.off()
```

**Test Buttons:**
```python
from gpiozero import Button
btn_ptt = Button(20)
btn_cancel = Button(21)
print("PTT pressed:", btn_ptt.is_pressed)
print("Cancel pressed:", btn_cancel.is_pressed)
```

## Common Issues

**LEDs not lighting:**
- Check resistor orientation (not polarized)
- Verify long leg is connected to GPIO
- Check for 3.3V on GPIO pin

**Buttons not responding:**
- Ensure pull-up is enabled in code
- Verify button is momentary (not latching)
- Check for loose connections

**LEDs too bright/dim:**
- 220Ω is standard, try 330Ω if too bright
- Try 150Ω if too dim (but don't exceed LED rating)