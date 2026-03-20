"""Configuration settings for Pi Audio Client."""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yaml"


class ServerConfig(BaseModel):
    """Server configuration.

    Set via config.yaml or environment variables:
      PI_SERVER_URL, PI_API_KEY, PI_DEVICE_ID
    """
    url: str = Field(default="http://localhost:8099", description="Hermes server URL")
    api_key: Optional[str] = Field(default=None, description="API key for server")
    device_id: str = Field(default="pi-audio-1", description="Device ID for session tracking")


class AudioConfig(BaseModel):
    """Audio configuration."""
    input_device: Optional[str] = Field(default=None, description="Input device name (None = default)")
    output_device: Optional[str] = Field(default=None, description="Output device name (None = default)")
    sample_rate: int = Field(default=16000, description="Sample rate in Hz")
    chunk_size: int = Field(default=1024, description="Audio chunk size")


class GPIOConfig(BaseModel):
    """GPIO configuration.
    
    Default pins tested and working on Pi Zero W:
    - GPIO 6: Green LED
    - GPIO 13: Red LED  
    - GPIO 19: PTT Button
    - GPIO 5: Cancel Button
    """
    led_idle: int = Field(default=6, description="GPIO pin for idle LED (green)")
    led_listening: int = Field(default=13, description="GPIO pin for listening LED (red)")
    button_ptt: int = Field(default=19, description="GPIO pin for push-to-talk button")
    button_cancel: int = Field(default=5, description="GPIO pin for cancel button")


class StateConfig(BaseModel):
    """Runtime interaction thresholds."""
    hold_threshold: float = Field(default=0.5, description="Seconds to hold PTT before recording")
    max_recording_secs: int = Field(default=30, description="Maximum recording time in seconds")
    timeout_idle: int = Field(default=30, description="Reserved for future idle timeout handling")
    timeout_speaking: int = Field(default=60, description="Reserved for future speaking timeout handling")


class Config(BaseModel):
    """Main configuration."""
    server: ServerConfig = Field(default_factory=ServerConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    gpio: GPIOConfig = Field(default_factory=GPIOConfig)
    state: StateConfig = Field(default_factory=StateConfig)
    debug_log_transcripts: bool = Field(
        default=False,
        description="Log transcript and response text content when debugging",
    )

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Config":
        """Load configuration from YAML file."""
        path = path or CONFIG_PATH
        
        if not path.exists():
            # Create default config
            config = cls()
            config.save(path)
            return config
        
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        
        return cls(**data)

    def save(self, path: Optional[Path] = None) -> None:
        """Save configuration to YAML file."""
        path = path or CONFIG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)

    def __str__(self) -> str:
        """String representation."""
        return f"Config(server={self.server.url}, audio_sr={self.audio.sample_rate}, gpio_ptt={self.gpio.button_ptt})"


# Global config instance
_config: Optional[Config] = None


def _apply_env_overrides(config: Config) -> Config:
    """Apply environment variable overrides to a config object."""
    if url := os.environ.get("PI_SERVER_URL"):
        config.server.url = url
    if api_key := os.environ.get("PI_API_KEY"):
        config.server.api_key = api_key
    if device_id := os.environ.get("PI_DEVICE_ID"):
        config.server.device_id = device_id
    if hold_threshold := os.environ.get("PI_HOLD_THRESHOLD"):
        config.state.hold_threshold = float(hold_threshold)
    if max_recording := os.environ.get("PI_MAX_RECORDING_SECS"):
        config.state.max_recording_secs = int(max_recording)
    if debug_transcripts := os.environ.get("PI_DEBUG_LOG_TRANSCRIPTS"):
        config.debug_log_transcripts = debug_transcripts.lower() in ("1", "true", "yes", "on")
    return config


def load_config(path: Optional[Path] = None) -> Config:
    """Get or load configuration.

    Environment variables override config.yaml values:
      PI_SERVER_URL, PI_API_KEY, PI_DEVICE_ID
    """
    global _config
    if _config is None:
        _config = _apply_env_overrides(Config.load(path))
    return _config


def reload_config(path: Optional[Path] = None) -> Config:
    """Force reload configuration."""
    global _config
    _config = _apply_env_overrides(Config.load(path))
    return _config
