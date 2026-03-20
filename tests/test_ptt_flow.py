"""Tests for PiAudioClient press-to-talk and playback flow."""

import sys
import time
from threading import Thread
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("gpiozero", MagicMock())
sys.modules.setdefault("pyaudio", MagicMock())
sys.modules.setdefault("pydantic", MagicMock())
sys.modules.setdefault("yaml", MagicMock())
sys.modules.setdefault("requests", MagicMock())

from src.main import PiAudioClient


def make_config(debug_log_transcripts: bool = False):
    """Build a minimal config object for PiAudioClient tests."""
    return SimpleNamespace(
        gpio=SimpleNamespace(
            led_idle=17,
            led_listening=18,
            button_ptt=20,
            button_cancel=21,
        ),
        audio=SimpleNamespace(
            sample_rate=16000,
            chunk_size=1024,
            input_device=None,
            output_device=None,
        ),
        server=SimpleNamespace(
            url="http://localhost:8099",
            api_key="test-key",
            device_id="test-device",
        ),
        state=SimpleNamespace(
            hold_threshold=0.5,
            max_recording_secs=30,
            timeout_idle=30,
            timeout_speaking=60,
        ),
        debug_log_transcripts=debug_log_transcripts,
    )


@pytest.fixture
def client():
    """Create a PiAudioClient with mocked hardware."""
    instance = PiAudioClient(make_config())
    instance.led = MagicMock()
    instance.audio_input = MagicMock()
    instance.audio_input.read_chunk.return_value = np.zeros(1024, dtype=np.int16)
    instance.audio_output = MagicMock()
    instance.hermes = MagicMock()
    instance.hermes.health_check.return_value = True
    instance.hermes.send_audio_and_get_response.return_value = (
        "Hello world",
        np.zeros(2048, dtype=np.int16),
    )
    return instance


def wait_for(condition, timeout: float = 1.0) -> None:
    """Poll until a condition becomes true."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met before timeout")


def mark_recording_active(client) -> None:
    """Simulate an active hold without starting the real recording thread."""
    client._recording = True
    client._record_thread = None


def test_press_does_not_start_recording_until_hold_threshold(client):
    """A press only marks the start time; recording begins after the hold threshold."""
    before = time.time()

    client._on_ptt_pressed()

    assert client._recording is False
    assert client._record_thread is None
    assert client._press_time >= before
    client.led.set_listening.assert_not_called()


def test_tap_release_plays_queued_message_without_sending_audio(client):
    """A tap should dequeue a response instead of recording and sending audio."""
    playback = MagicMock()
    client._play_response = playback
    client._message_queue.put(("Queued reply", np.ones(128, dtype=np.int16)))
    client._on_ptt_pressed()

    client._on_ptt_released()

    wait_for(lambda: playback.called)
    client.hermes.send_audio_and_get_response.assert_not_called()
    assert client._message_queue.empty()


def test_hold_release_sends_audio_to_hermes_and_queues_response(client):
    """A held PTT interaction should send buffered audio and queue the TTS response."""
    client._on_ptt_pressed()
    mark_recording_active(client)

    with client._buffer_lock:
        client._recording_buffer = [
            np.zeros(1024, dtype=np.int16),
            np.ones(1024, dtype=np.int16),
        ]

    client._on_ptt_released()

    wait_for(lambda: client.hermes.send_audio_and_get_response.called)
    client.hermes.send_audio_and_get_response.assert_called_once()
    sent_audio = client.hermes.send_audio_and_get_response.call_args.args[0]
    assert len(sent_audio) == 2048
    assert client._pending_count == 0
    queued_text, queued_audio = client._message_queue.get_nowait()
    assert queued_text == "Hello world"
    assert len(queued_audio) == 2048


def test_recording_buffer_cleared_after_hold_release(client):
    """Buffered chunks should be cleared after a held interaction is submitted."""
    client._on_ptt_pressed()
    mark_recording_active(client)

    with client._buffer_lock:
        client._recording_buffer = [np.zeros(1024, dtype=np.int16) for _ in range(3)]

    client._on_ptt_released()

    wait_for(lambda: client.hermes.send_audio_and_get_response.called)
    with client._buffer_lock:
        assert client._recording_buffer == []


def test_play_response_is_serialized_across_threads(client):
    """Playback threads should not overlap writes to the audio output."""
    active_calls = 0
    max_active_calls = 0

    def write_chunk(_chunk):
        nonlocal active_calls, max_active_calls
        active_calls += 1
        max_active_calls = max(max_active_calls, active_calls)
        time.sleep(0.01)
        active_calls -= 1

    client.audio_output.write_chunk.side_effect = write_chunk
    audio = np.arange(4096, dtype=np.int16)

    first = Thread(target=client._play_response, args=(audio,), daemon=True)
    second = Thread(target=client._play_response, args=(audio,), daemon=True)
    first.start()
    second.start()
    first.join(timeout=1.0)
    second.join(timeout=1.0)

    assert not first.is_alive()
    assert not second.is_alive()
    assert max_active_calls == 1


def test_transcript_logging_is_gated_by_debug_flag(client, caplog):
    """Response text should only be logged when debug transcript logging is enabled."""
    secret = "top secret response"
    client.hermes.send_audio_and_get_response.return_value = (secret, np.zeros(0, dtype=np.int16))
    caplog.set_level("INFO")

    client._hermes_worker(np.zeros(64, dtype=np.int16))

    assert secret not in caplog.text

    debug_client = PiAudioClient(make_config(debug_log_transcripts=True))
    debug_client.led = MagicMock()
    debug_client.audio_input = MagicMock()
    debug_client.audio_output = MagicMock()
    debug_client.hermes = MagicMock()
    debug_client.hermes.send_audio_and_get_response.return_value = (
        secret,
        np.zeros(0, dtype=np.int16),
    )

    client_log_start = len(caplog.records)
    debug_client._hermes_worker(np.zeros(64, dtype=np.int16))
    new_messages = " ".join(record.getMessage() for record in caplog.records[client_log_start:])
    assert secret in new_messages


def test_dual_button_hold_triggers_reset_after_threshold(client):
    """Holding both buttons long enough should trigger a reboot path once."""
    client._trigger_system_reset = MagicMock()

    assert client._handle_dual_button_reset(True, True, now=10.0) is True
    client._trigger_system_reset.assert_not_called()

    assert client._handle_dual_button_reset(True, True, now=12.9) is True
    client._trigger_system_reset.assert_not_called()

    assert client._handle_dual_button_reset(True, True, now=13.1) is True
    client._trigger_system_reset.assert_called_once()


def test_dual_button_hold_resets_when_one_button_released(client):
    """Releasing either button should cancel the pending reset timer."""
    client._trigger_system_reset = MagicMock()

    assert client._handle_dual_button_reset(True, True, now=20.0) is True
    assert client._handle_dual_button_reset(True, False, now=21.0) is False
    assert client._handle_dual_button_reset(True, True, now=22.0) is True
    assert client._handle_dual_button_reset(True, True, now=24.9) is True

    client._trigger_system_reset.assert_not_called()
