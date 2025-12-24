"""Configuration dataclasses for Sphero RVR MCP server."""

import os
from dataclasses import dataclass, field


@dataclass
class SerialConfig:
    """Serial port configuration for RVR connection."""
    port: str = "/dev/ttyS0"
    baud_rate: int = 115200


@dataclass
class SafetyConfig:
    """Safety system configuration."""
    default_max_speed_percent: float = 50.0
    command_timeout_seconds: float = 5.0
    enable_collision_detection: bool = True
    collision_threshold_g: float = 2.0
    auto_stop_on_disconnect: bool = True


@dataclass
class SensorConfig:
    """Sensor streaming configuration."""
    default_streaming_interval_ms: int = 250
    min_streaming_interval_ms: int = 50
    sensor_data_ttl_seconds: float = 2.0


@dataclass
class RvrConfig:
    """Main configuration for RVR MCP server."""
    serial: SerialConfig = field(default_factory=SerialConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    sensors: SensorConfig = field(default_factory=SensorConfig)
    wake_timeout_seconds: float = 5.0
    reconnect_max_attempts: int = 3
    reconnect_backoff_base_seconds: float = 1.0


def load_config_from_env() -> RvrConfig:
    """Load configuration from environment variables.

    Environment variables:
        RVR_SERIAL_PORT: Serial port (default: /dev/ttyS0)
        RVR_BAUD_RATE: Baud rate (default: 115200)
        RVR_MAX_SPEED_PERCENT: Default max speed 0-100 (default: 50)
        RVR_COMMAND_TIMEOUT: Auto-stop timeout in seconds (default: 5.0)
        RVR_SENSOR_INTERVAL: Sensor streaming interval in ms (default: 250)

    Returns:
        RvrConfig with values from environment or defaults.
    """
    config = RvrConfig()

    # Serial config
    if port := os.environ.get("RVR_SERIAL_PORT"):
        config.serial.port = port
    if baud := os.environ.get("RVR_BAUD_RATE"):
        config.serial.baud_rate = int(baud)

    # Safety config
    if max_speed := os.environ.get("RVR_MAX_SPEED_PERCENT"):
        config.safety.default_max_speed_percent = float(max_speed)
    if timeout := os.environ.get("RVR_COMMAND_TIMEOUT"):
        config.safety.command_timeout_seconds = float(timeout)

    # Sensor config
    if interval := os.environ.get("RVR_SENSOR_INTERVAL"):
        config.sensors.default_streaming_interval_ms = int(interval)

    return config
