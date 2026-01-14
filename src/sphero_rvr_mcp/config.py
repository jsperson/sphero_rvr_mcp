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
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_duration_seconds: float = 30.0


@dataclass
class ObservabilityConfig:
    """Observability configuration."""
    log_level: str = "INFO"
    log_format: str = "json"  # json or console
    metrics_enabled: bool = True
    metrics_port: int = 9090


@dataclass
class RvrConfig:
    """Main configuration for RVR MCP server."""
    serial: SerialConfig = field(default_factory=SerialConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    sensors: SensorConfig = field(default_factory=SensorConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    wake_timeout_seconds: float = 5.0
    reconnect_max_attempts: int = 3
    reconnect_backoff_base_seconds: float = 1.0
    command_queue_size: int = 100
    event_bus_queue_size: int = 1000


def load_config_from_env() -> dict:
    """Load configuration from environment variables.

    Environment variables:
        RVR_SERIAL_PORT: Serial port (default: /dev/ttyS0)
        RVR_BAUD_RATE: Baud rate (default: 115200)
        RVR_MAX_SPEED_PERCENT: Default max speed 0-100 (default: 50)
        RVR_COMMAND_TIMEOUT: Auto-stop timeout in seconds (default: 5.0)
        RVR_SENSOR_INTERVAL: Sensor streaming interval in ms (default: 250)
        RVR_LOG_LEVEL: Log level (default: INFO)
        RVR_LOG_FORMAT: Log format json or console (default: json)
        RVR_METRICS_ENABLED: Enable metrics (default: true)
        RVR_CIRCUIT_BREAKER_FAILURE_THRESHOLD: Circuit breaker failure threshold (default: 5)
        RVR_CIRCUIT_BREAKER_TIMEOUT: Circuit breaker timeout seconds (default: 30)

    Returns:
        Config dict with values from environment or defaults.
    """
    config = {
        "serial_port": os.environ.get("RVR_SERIAL_PORT", "/dev/ttyS0"),
        "baud_rate": int(os.environ.get("RVR_BAUD_RATE", "115200")),
        "max_speed_percent": float(os.environ.get("RVR_MAX_SPEED_PERCENT", "50.0")),
        "command_timeout": float(os.environ.get("RVR_COMMAND_TIMEOUT", "5.0")),
        "sensor_interval": int(os.environ.get("RVR_SENSOR_INTERVAL", "250")),
        "log_level": os.environ.get("RVR_LOG_LEVEL", "INFO"),
        "log_format": os.environ.get("RVR_LOG_FORMAT", "json"),
        "metrics_enabled": os.environ.get("RVR_METRICS_ENABLED", "true").lower() == "true",
        "circuit_breaker_failure_threshold": int(os.environ.get("RVR_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")),
        "circuit_breaker_timeout": float(os.environ.get("RVR_CIRCUIT_BREAKER_TIMEOUT", "30.0")),
    }

    return config
