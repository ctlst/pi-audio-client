"""Button control for Pi Audio Client."""

from gpiozero import Button
from signal import pause
from threading import Lock, Event
from typing import Optional, Callable
import logging
import time

logger = logging.getLogger(__name__)


class ButtonController:
    """Controller for GPIO buttons."""
    
    def __init__(self, ptt_pin: int, cancel_pin: Optional[int] = None):
        """Initialize button controller.
        
        Args:
            ptt_pin: GPIO pin for push-to-talk button
            cancel_pin: GPIO pin for cancel button (optional)
        """
        self.ptt_button = Button(ptt_pin, pull_up=True, bounce_time=0.05)
        self.cancel_button: Optional[Button] = None
        self._cancel_pin = cancel_pin

        if cancel_pin:
            self.cancel_button = Button(cancel_pin, pull_up=True, bounce_time=0.1)
        
        self._event_lock = Lock()
        self._ptt_pressed = Event()
        self._cancel_pressed = Event()
        self._ptt_callback: Optional[Callable[[], None]] = None
        self._cancel_callback: Optional[Callable[[], None]] = None
        
        # Set up callbacks
        self.ptt_button.when_pressed = self._on_ptt_pressed
        self.ptt_button.when_released = self._on_ptt_released
        
        if self.cancel_button:
            self.cancel_button.when_pressed = self._on_cancel_pressed
    
    def _on_ptt_pressed(self) -> None:
        """Handle PTT button press."""
        with self._event_lock:
            self._ptt_pressed.set()
            logger.debug("PTT button pressed")
        
        if self._ptt_callback:
            self._ptt_callback()
    
    def _on_ptt_released(self) -> None:
        """Handle PTT button release."""
        with self._event_lock:
            self._ptt_pressed.clear()
            logger.debug("PTT button released")
    
    def _on_cancel_pressed(self) -> None:
        """Handle cancel button press."""
        with self._event_lock:
            self._cancel_pressed.set()
            logger.debug("Cancel button pressed")
        
        if self._cancel_callback:
            self._cancel_callback()
    
    def set_ptt_callback(self, callback: Callable[[], None]) -> None:
        """Set callback for PTT button press."""
        self._ptt_callback = callback
    
    def set_cancel_callback(self, callback: Callable[[], None]) -> None:
        """Set callback for cancel button press."""
        self._cancel_callback = callback
    
    def is_ptt_pressed(self) -> bool:
        """Check if PTT button is currently pressed."""
        return self.ptt_button.is_pressed
    
    def wait_for_ptt(self, timeout: Optional[float] = None) -> bool:
        """Wait for PTT button press.
        
        Args:
            timeout: Maximum time to wait (None = wait forever)
            
        Returns:
            True if button was pressed, False if timeout
        """
        try:
            self._ptt_pressed.wait(timeout=timeout)
            return True
        except (KeyboardInterrupt, Exception):
            return False
    
    def wait_for_cancel(self, timeout: Optional[float] = None) -> bool:
        """Wait for cancel button press.
        
        Args:
            timeout: Maximum time to wait
            
        Returns:
            True if button was pressed, False if timeout
        """
        if not self.cancel_button:
            return False
            
        try:
            self._cancel_pressed.wait(timeout=timeout)
            return True
        except (KeyboardInterrupt, Exception):
            return False
    
    def cleanup(self) -> None:
        """Clean up button resources."""
        self.ptt_button.close()
        if self.cancel_button:
            self.cancel_button.close()
        logger.debug("Button controller cleanup complete")


class ButtonEventHandler:
    """Event handler for button state changes."""
    
    def __init__(self):
        self._ptt_callbacks = []
        self._cancel_callbacks = []
        
    def on_ptt_press(self, callback: Callable[[], None]) -> None:
        """Register callback for PTT press."""
        self._ptt_callbacks.append(callback)
    
    def on_ptt_release(self, callback: Callable[[], None]) -> None:
        """Register callback for PTT release."""
        pass
    
    def on_cancel_press(self, callback: Callable[[], None]) -> None:
        """Register callback for cancel press."""
        self._cancel_callbacks.append(callback)
    
    def execute_ptt_press(self) -> None:
        """Execute all PTT press callbacks."""
        for callback in self._ptt_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"PTT callback error: {e}")
    
    def execute_cancel_press(self) -> None:
        """Execute all cancel press callbacks."""
        for callback in self._cancel_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Cancel callback error: {e}")