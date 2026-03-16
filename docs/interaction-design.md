# Interaction Design

## LED States

| State | Green LED | Red LED |
|-------|-----------|---------|
| Idle (no messages) | Solid | Off |
| New message waiting | Blinking | Off |
| Recording (PTT held) | Off | Solid |
| Processing (waiting for hermes) | Off | Blinking slow |
| Playing audio response | Blinking | Off |
| Error | Off | Blinking fast |

## PTT Button (GPIO 25)

| Action | Behavior |
|--------|----------|
| **Hold** | Record audio, send to hermes on release. Can queue multiple messages without waiting for response. |
| **Single tap** | Play the latest stored response. Green blink → playback → idle. |

## Cancel/Action Button (GPIO 26)

| Action | Behavior |
|--------|----------|
| **Single tap** | Stop current audio playback. |
| **Double tap** | Replay last message. |
| **Long press** | TBD — future feature. |
| **Triple tap** | TBD — future feature. |

## Message Queue Behavior

- Hermes responses take 10-30 seconds. User shouldn't have to wait.
- When a response arrives, it goes into a message queue.
- Green LED blinks to indicate new message(s) waiting.
- User taps PTT to play the next message.
- User can hold PTT to send another message while previous ones are still processing.
- Multiple messages can be in-flight simultaneously.
- Responses play in order when user taps PTT.

## Flow Example

1. User holds PTT → red solid → speaks → releases → red blink (processing)
2. User holds PTT again → red solid → speaks → releases → red blink (processing)
3. First response arrives → green blink (new message)
4. User taps PTT → plays first response → green blink (still have second)
5. Second response arrives (already waiting)
6. User taps PTT → plays second response → green solid (idle, no messages)

## Future Ideas

- Long press cancel: TBD
- Triple tap cancel: TBD
- OLED display: show status, waveform, progress messages from hermes
- I2S audio board: GPIO-based audio, frees USB for gadget mode
