"""Tests for GPIO module."""

import pytest
from unittest.mock import MagicMock, patch


def test_led_controller():
    """Test LED controller state changes."""
    with patch('gpiozero.LED') as mock_led:
        from src.gpio.led import LEDController
        
        controller = LEDController(idle_pin=17, listening_pin=18)
        
        controller.set_idle()
        mock_led.assert_called()
        
        controller.set_listening()
        
        controller.set_processing()
        
        controller.set_speaking()
        
        controller.cleanup()


def test_button_controller():
    """Test button controller."""
    with patch('gpiozero.Button') as mock_button:
        from src.gpio.buttons import ButtonController
        
        controller = ButtonController(ptt_pin=20, cancel_pin=21)
        
        assert controller.is_ptt_pressed() is False
        
        controller.cleanup()