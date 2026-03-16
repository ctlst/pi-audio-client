"""LED control for Pi Audio Client."""

from gpiozero import LED
from threading import Lock
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class LEDController:
    """Controller for GPIO LEDs."""
    
    def __init__(self, idle_pin: int, listening_pin: int):
        """Initialize LED controller.
        
        Args:
            idle_pin: GPIO pin for idle LED (green)
            listening_pin: GPIO pin for listening LED (red)
        """
        self.idle_led = LED(idle_pin)
        self.listening_led = LED(listening_pin)
        self._state_lock = Lock()
        self._current_state: Optional[str] = None
        
    def set_idle(self) -> None:
        """Set LED to idle state (green on, red off)."""
        with self._state_lock:
            self.idle_led.on()
            self.listening_led.off()
            self._current_state = "idle"
            logger.debug("LED state: idle")
    
    def set_listening(self) -> None:
        """Set LED to listening state (red on, green off)."""
        with self._state_lock:
            self.idle_led.off()
            self.listening_led.on()
            self._current_state = "listening"
            logger.debug("LED state: listening")
    
    def set_processing(self) -> None:
        """Set LED to processing state (both off or blinking)."""
        with self._state_lock:
            self.idle_led.off()
            self.listening_led.blink(on_time=0.1, off_time=0.1)
            self._current_state = "processing"
            logger.debug("LED state: processing")
    
    def set_speaking(self) -> None:
        """Set LED to speaking state (green blinking)."""
        with self._state_lock:
            self.idle_led.blink(on_time=0.2, off_time=0.2)
            self.listening_led.off()
            self._current_state = "speaking"
            logger.debug("LED state: speaking")
    
    def set_error(self) -> None:
        """Set LED to error state (red blinking fast)."""
        with self._state_lock:
            self.idle_led.off()
            self.listening_led.blink(on_time=0.05, off_time=0.05)
            self._current_state = "error"
            logger.debug("LED state: error")
    
    def reset(self) -> None:
        """Reset all LEDs (green on)."""
        self.set_idle()
    
    def get_state(self) -> Optional[str]:
        """Get current LED state."""
        with self._state_lock:
            return self._current_state
    
    def cleanup(self) -> None:
        """Clean up LED resources."""
        self.idle_led.close()
        self.listening_led.close()
        logger.debug("LED controller cleanup complete")