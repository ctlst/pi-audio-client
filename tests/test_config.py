"""Tests for configuration loading and reload behavior."""

from pathlib import Path
import importlib.util

import pytest

if importlib.util.find_spec("pydantic") is None or importlib.util.find_spec("yaml") is None:
    pytestmark = pytest.mark.skip(reason="pydantic and pyyaml are required for config loading tests")
else:
    from src.config.settings import CONFIG_PATH, load_config, reload_config
    import src.config.settings as settings


@pytest.fixture(autouse=True)
def reset_cached_config(monkeypatch):
    """Reset cached config and env overrides between tests."""
    settings._config = None
    for name in (
        "PI_SERVER_URL",
        "PI_API_KEY",
        "PI_DEVICE_ID",
        "PI_HOLD_THRESHOLD",
        "PI_MAX_RECORDING_SECS",
        "PI_DEBUG_LOG_TRANSCRIPTS",
    ):
        monkeypatch.delenv(name, raising=False)
    yield
    settings._config = None


def write_config(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_reload_config_reapplies_environment_overrides(tmp_path, monkeypatch):
    """reload_config should behave like load_config and keep env overrides active."""
    config_path = tmp_path / "config.yaml"
    write_config(
        config_path,
        """
server:
  url: "http://config-file:8099"
  api_key: "file-key"
  device_id: "file-device"
state:
  hold_threshold: 0.75
  max_recording_secs: 45
debug_log_transcripts: false
""".strip()
        + "\n",
    )

    monkeypatch.setenv("PI_SERVER_URL", "http://env-server:9000")
    monkeypatch.setenv("PI_API_KEY", "env-key")
    monkeypatch.setenv("PI_DEVICE_ID", "env-device")
    monkeypatch.setenv("PI_HOLD_THRESHOLD", "1.25")
    monkeypatch.setenv("PI_MAX_RECORDING_SECS", "12")
    monkeypatch.setenv("PI_DEBUG_LOG_TRANSCRIPTS", "true")

    loaded = load_config(config_path)
    reloaded = reload_config(config_path)

    for config in (loaded, reloaded):
        assert config.server.url == "http://env-server:9000"
        assert config.server.api_key == "env-key"
        assert config.server.device_id == "env-device"
        assert config.state.hold_threshold == pytest.approx(1.25)
        assert config.state.max_recording_secs == 12
        assert config.debug_log_transcripts is True


def test_default_config_path_constant():
    """CONFIG_PATH should still point at config.yaml in the repo root."""
    assert CONFIG_PATH.name == "config.yaml"
