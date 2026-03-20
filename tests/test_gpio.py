"""Tests for GPIO wrappers."""

import sys
from unittest.mock import MagicMock

sys.modules.setdefault("gpiozero", MagicMock())

from src.gpio.buttons import ButtonController
from src.gpio.led import LEDController


def test_led_controller_state_changes():
    """LED controller should update internal state for each transition."""
    controller = LEDController(idle_pin=17, listening_pin=18)

    controller.set_idle()
    assert controller.get_state() == "idle"

    controller.set_listening()
    assert controller.get_state() == "listening"

    controller.set_processing()
    assert controller.get_state() == "processing"

    controller.set_speaking()
    assert controller.get_state() == "speaking"

    controller.cleanup()


def test_button_controller_waits_return_false_on_timeout():
    """Waiting helpers should reflect Event.wait() rather than always returning success."""
    controller = ButtonController(ptt_pin=20, cancel_pin=21)

    assert controller.wait_for_ptt(timeout=0.01) is False
    assert controller.wait_for_cancel(timeout=0.01) is False

    controller._on_ptt_pressed()
    controller._on_cancel_pressed()
    assert controller.wait_for_ptt(timeout=0.01) is True
    assert controller.wait_for_cancel(timeout=0.01) is True

    controller.cleanup()
