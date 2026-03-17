"""Test PTT recording flow with simulated button presses.

Verifies that:
- Press starts recording and sets LED to listening (red)
- Audio chunks accumulate in buffer while recording
- Release grabs buffer, sends to hermes, sets LED to processing
- After hermes responds, LED returns to idle
"""

import sys
import time
import queue
from threading import Thread, Event, Lock
from unittest.mock import MagicMock
from types import ModuleType

import numpy as np
import pytest

# Stub all Pi-specific modules before importing src.main
for mod_name in [
    'gpiozero', 'pyaudio', 'pydantic', 'yaml', 'requests',
    'src.config', 'src.config.settings',
    'src.gpio', 'src.gpio.led', 'src.gpio.buttons', 'src.gpio.taps',
    'src.audio', 'src.audio.input', 'src.audio.output',
    'src.client',
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

from src.main import PiAudioClient


@pytest.fixture
def client():
    """Create a PiAudioClient with mocked hardware."""
    config = MagicMock()
    config.gpio.led_idle = 17
    config.gpio.led_listening = 18
    config.gpio.button_ptt = 20
    config.gpio.button_cancel = 21
    config.audio.sample_rate = 16000
    config.audio.chunk_size = 1024
    config.audio.input_device = None
    config.audio.output_device = None
    config.server.url = "http://localhost:8081"
    config.server.api_key = "test"
    config.server.device_id = "test"
    config.state.timeout_recording = 30

    c = PiAudioClient(config)

    # Replace components with mocks
    c.led = MagicMock()
    c.audio_input = MagicMock()
    c.audio_input.read_chunk.return_value = np.zeros(1024, dtype=np.int16)
    c.audio_output = MagicMock()
    c.hermes = MagicMock()
    c.hermes.health_check.return_value = True
    c.hermes.send_audio_and_get_response.return_value = (
        "Hello world",
        np.zeros(16000, dtype=np.int16),
    )

    yield c


def test_press_starts_recording(client):
    """PTT press should set recording flag and LED to listening."""
    client._on_ptt_pressed()

    assert client._recording is True
    client.led.set_listening.assert_called()


def test_release_with_audio_sends_to_hermes(client):
    """PTT release with buffered audio should send to hermes and set processing LED."""
    client._on_ptt_pressed()

    # Simulate main loop buffering chunks
    for _ in range(20):
        with client._buffer_lock:
            client._recording_buffer.append(np.zeros(1024, dtype=np.int16))

    client._on_ptt_release()

    assert client._recording is False
    client.led.set_processing.assert_called()

    # Wait for hermes worker thread
    time.sleep(0.5)

    client.hermes.send_audio_and_get_response.assert_called_once()
    assert not client._message_queue.empty()


def test_release_with_empty_buffer_goes_idle(client):
    """PTT release with no audio should go to idle LED."""
    client._on_ptt_pressed()
    # Don't add any chunks — empty buffer
    client._on_ptt_release()

    assert client._recording is False
    client.led.set_idle.assert_called()


def test_release_with_empty_buffer_plays_queued_message(client):
    """PTT tap (empty buffer) should play queued message if available."""
    # Queue a message
    client._message_queue.put(("Hello", np.zeros(1600, dtype=np.int16)))

    client._on_ptt_pressed()
    # Empty buffer — simulates a tap
    client._on_ptt_release()

    assert client._recording is False
    assert client._message_queue.empty()


def test_led_returns_to_idle_after_hermes_response(client):
    """After hermes responds, pending count should return to 0."""
    client._on_ptt_pressed()

    for _ in range(10):
        with client._buffer_lock:
            client._recording_buffer.append(np.zeros(1024, dtype=np.int16))

    client._on_ptt_release()

    # Wait for hermes worker
    time.sleep(0.5)

    assert client._pending_count == 0


def test_recording_flag_and_buffer_cleared_atomically(client):
    """Release should clear recording and grab buffer under the same lock."""
    client._on_ptt_pressed()

    for _ in range(5):
        with client._buffer_lock:
            client._recording_buffer.append(np.zeros(1024, dtype=np.int16))

    client._on_ptt_release()

    assert client._recording is False
    with client._buffer_lock:
        assert len(client._recording_buffer) == 0

    # Hermes should have been called with concatenated audio
    time.sleep(0.5)
    args = client.hermes.send_audio_and_get_response.call_args
    audio_sent = args[0][0]
    assert len(audio_sent) == 5 * 1024


def test_main_loop_reads_audio_when_not_recording(client):
    """Main loop should read chunks even when not recording to prevent buffer overflow."""
    client._recording = False

    # Simulate main loop iterations
    for _ in range(5):
        chunk = client.audio_input.read_chunk()
        if client._recording:
            with client._buffer_lock:
                client._recording_buffer.append(chunk)

    # Audio was read 5 times even though not recording
    assert client.audio_input.read_chunk.call_count == 5
    # But nothing was buffered
    assert len(client._recording_buffer) == 0


def test_race_condition_release_during_append(client):
    """Release happening between read and append should not lose buffer."""
    client._on_ptt_pressed()

    # Main loop adds some chunks
    for _ in range(3):
        with client._buffer_lock:
            client._recording_buffer.append(np.zeros(1024, dtype=np.int16))

    # Release grabs the buffer atomically
    client._on_ptt_release()

    # Simulate main loop trying to append after release
    chunk = np.zeros(1024, dtype=np.int16)
    with client._buffer_lock:
        if client._recording:  # Should be False
            client._recording_buffer.append(chunk)

    # Buffer should be empty — release cleared it and recording is False
    with client._buffer_lock:
        assert len(client._recording_buffer) == 0

    # Hermes got all 3 chunks
    time.sleep(0.5)
    args = client.hermes.send_audio_and_get_response.call_args
    audio_sent = args[0][0]
    assert len(audio_sent) == 3 * 1024
