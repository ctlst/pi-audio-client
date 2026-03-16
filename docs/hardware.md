# Hardware Wiring

## GPIO Pinout

| Function       | GPIO | Physical Pin |
|---------------|------|-------------|
| Green LED      | 6    | 31          |
| Red LED        | 13   | 33          |
| PTT Button     | 25   | 22          |
| Cancel Button  | 26   | 37          |

## Pin Header Reference

```
Pi Zero W GPIO Header (pin numbers)
┌──────────────────────────────────────────────────────┐
│ 1:3.3V  2:5V   3:GPIO2  4:5V   5:GPIO3  6:GND      │
│ 7:GPIO4 8:GPIO14 9:GND  10:GPIO15 11:GPIO17 12:GPIO18│
│ 13:GPIO27 14:GND  15:GPIO22 16:GPIO23 17:3.3V 18:GPIO24│
│ 19:GPIO10 20:GND  21:GPIO9  22:GPIO25 23:GPIO8  24:GPIO7│
│ 25:GND  26:GPIO21 27:GPIO16 28:GPIO20 29:GPIO5  30:GND│
│ 31:GPIO6 32:GPIO12 33:GPIO13 34:GND  35:GPIO19 36:GPIO26│
│ 37:GPIO26 38:GPIO20 39:GND  40:GPIO21               │
└──────────────────────────────────────────────────────┘
```

## Wiring Diagram

```
┌─────────────────────────────────────────────────────┐
│  Pi Zero W Breadboard Setup                         │
│                                                     │
│  Pin 31 (GPIO 6)  ── Green LED ── 220R ─────── GND │
│  Pin 33 (GPIO 13) ── Red LED   ── 220R ─────── GND │
│                                                     │
│  Pin 22 (GPIO 25) ── PTT Button ────────────── GND │
│  Pin 37 (GPIO 26) ── Cancel Button ─────────── GND │
│                                                     │
│  USB Port ── USB headphones (mic + speaker)         │
└─────────────────────────────────────────────────────┘
```

### LEDs

Connect GPIO pin to LED anode (long leg). Connect cathode (short leg) through a 220 ohm resistor to GND.

### Buttons

Connect one leg to the GPIO pin and the other leg to GND. Use **external 10k ohm pull-up resistors** from each button GPIO pin to 3.3V. The internal pull-ups on the Pi are weak (~50k ohm) and pick up noise on longer wires or breadboard setups, causing phantom button presses. External 10k ohm pull-ups solve this reliably.

```
3.3V ── 10kR ──┬── GPIO pin
               │
            Button
               │
              GND
```

## Configuration

```yaml
gpio:
  led_idle: 6
  led_listening: 13
  button_ptt: 25
  button_cancel: 26
```

## Testing

```bash
# Test LEDs
python3 -c "from gpiozero import LED; LED(6).on(); input('Green on, press Enter'); LED(6).off()"
python3 -c "from gpiozero import LED; LED(13).on(); input('Red on, press Enter'); LED(13).off()"

# Test buttons
python3 -c "
from gpiozero import Button
import signal
btn = Button(25)
btn.when_pressed = lambda: print('PTT pressed')
btn.when_released = lambda: print('PTT released')
print('Press PTT button (Ctrl+C to exit)')
signal.pause()
"
```
