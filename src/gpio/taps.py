"""Tap detection for GPIO buttons.

Distinguishes between:
- Single tap (press < hold_threshold, no second tap within double_tap_window)
- Double tap (two taps within double_tap_window)
- Hold (press >= hold_threshold)
- Triple tap (three taps within triple_tap_window)
"""

import logging
import time
from threading import Timer
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class TapDetector:
    """Detects tap patterns on a gpiozero Button.

    Wires into when_pressed/when_released on the button and calls
    back with the detected action.
    """

    def __init__(
        self,
        button,
        on_hold: Optional[Callable] = None,
        on_hold_release: Optional[Callable] = None,
        on_single_tap: Optional[Callable] = None,
        on_double_tap: Optional[Callable] = None,
        on_triple_tap: Optional[Callable] = None,
        hold_threshold: float = 0.5,
        multi_tap_window: float = 0.4,
    ):
        """
        Args:
            button: gpiozero Button instance
            on_hold: Called when button is held past hold_threshold
            on_hold_release: Called when a held button is released
            on_single_tap: Called on single tap
            on_double_tap: Called on double tap
            on_triple_tap: Called on triple tap
            hold_threshold: Seconds before press counts as hold
            multi_tap_window: Seconds to wait for additional taps
        """
        self.button = button
        self.on_hold = on_hold
        self.on_hold_release = on_hold_release
        self.on_single_tap = on_single_tap
        self.on_double_tap = on_double_tap
        self.on_triple_tap = on_triple_tap
        self.hold_threshold = hold_threshold
        self.multi_tap_window = multi_tap_window

        self._press_time = 0.0
        self._is_holding = False
        self._tap_count = 0
        self._tap_timer: Optional[Timer] = None
        self._hold_timer: Optional[Timer] = None

        # Wire callbacks
        button.when_pressed = self._on_press
        button.when_released = self._on_release

    def _on_press(self) -> None:
        """Button pressed."""
        self._press_time = time.monotonic()
        self._is_holding = False

        # Start hold timer
        if self._hold_timer:
            self._hold_timer.cancel()
        self._hold_timer = Timer(self.hold_threshold, self._on_hold_detected)
        self._hold_timer.daemon = True
        self._hold_timer.start()

    def _on_hold_detected(self) -> None:
        """Hold threshold reached while button still pressed."""
        self._is_holding = True
        # Cancel any pending tap evaluation
        if self._tap_timer:
            self._tap_timer.cancel()
            self._tap_timer = None
        self._tap_count = 0
        logger.debug("Hold detected")
        if self.on_hold:
            self.on_hold()

    def _on_release(self) -> None:
        """Button released."""
        # Cancel hold timer
        if self._hold_timer:
            self._hold_timer.cancel()
            self._hold_timer = None

        if self._is_holding:
            # Was a hold — fire hold release
            self._is_holding = False
            logger.debug("Hold released")
            if self.on_hold_release:
                self.on_hold_release()
            return

        # Short press — count as tap
        press_duration = time.monotonic() - self._press_time
        if press_duration >= self.hold_threshold:
            # Somehow missed the hold detection — treat as hold release
            if self.on_hold_release:
                self.on_hold_release()
            return

        self._tap_count += 1
        logger.debug("Tap %d", self._tap_count)

        # Cancel previous tap timer and start new one
        if self._tap_timer:
            self._tap_timer.cancel()
        self._tap_timer = Timer(self.multi_tap_window, self._evaluate_taps)
        self._tap_timer.daemon = True
        self._tap_timer.start()

    def _evaluate_taps(self) -> None:
        """Called after multi_tap_window with no new taps."""
        count = self._tap_count
        self._tap_count = 0
        self._tap_timer = None

        if count >= 3:
            logger.debug("Triple tap")
            if self.on_triple_tap:
                self.on_triple_tap()
        elif count == 2:
            logger.debug("Double tap")
            if self.on_double_tap:
                self.on_double_tap()
        elif count == 1:
            logger.debug("Single tap")
            if self.on_single_tap:
                self.on_single_tap()

    def cleanup(self) -> None:
        """Cancel pending timers."""
        if self._tap_timer:
            self._tap_timer.cancel()
        if self._hold_timer:
            self._hold_timer.cancel()
