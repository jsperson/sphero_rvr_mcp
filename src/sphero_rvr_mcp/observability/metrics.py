"""Prometheus metrics for comprehensive observability.

This module provides metrics collection that enables monitoring of
performance, reliability, and system health.
"""

from prometheus_client import Counter, Histogram, Gauge, Enum, Info
from typing import Optional


# Command metrics
command_total = Counter(
    "rvr_commands_total",
    "Total number of commands executed",
    ["command_type", "status"],  # status: success, error, timeout
)

command_duration_seconds = Histogram(
    "rvr_command_duration_seconds",
    "Command execution duration in seconds",
    ["command_type"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

command_queue_depth = Gauge(
    "rvr_command_queue_depth",
    "Number of commands currently queued",
)

command_queue_full_total = Counter(
    "rvr_command_queue_full_total",
    "Number of times command queue reached capacity",
)

# Connection metrics
connection_state_enum = Enum(
    "rvr_connection_state",
    "Current connection state",
    states=["disconnected", "connecting", "connected", "reconnecting", "error"],
)

connection_uptime_seconds = Gauge(
    "rvr_connection_uptime_seconds",
    "Connection uptime in seconds",
)

connection_attempts_total = Counter(
    "rvr_connection_attempts_total",
    "Total connection attempts",
    ["result"],  # result: success, failure
)

reconnection_attempts_total = Counter(
    "rvr_reconnection_attempts_total",
    "Total reconnection attempts",
)

# Sensor metrics
sensor_data_age_milliseconds = Histogram(
    "rvr_sensor_data_age_milliseconds",
    "Age of sensor data in milliseconds",
    ["sensor"],
    buckets=(10, 25, 50, 100, 250, 500, 1000, 2000, 5000),
)

sensor_streaming_rate_hz = Gauge(
    "rvr_sensor_streaming_rate_hz",
    "Sensor streaming rate in Hz",
    ["sensor"],
)

sensor_streaming_active = Gauge(
    "rvr_sensor_streaming_active",
    "Whether sensor streaming is currently active",
)

sensor_events_total = Counter(
    "rvr_sensor_events_total",
    "Total sensor events received",
    ["sensor"],
)

# Safety metrics
emergency_stops_total = Counter(
    "rvr_emergency_stops_total",
    "Total number of emergency stops",
)

speed_limits_applied_total = Counter(
    "rvr_speed_limits_applied_total",
    "Number of times speed limit was applied",
)

command_timeouts_total = Counter(
    "rvr_command_timeouts_total",
    "Number of command timeouts",
    ["command_type"],
)

speed_limit_percent = Gauge(
    "rvr_speed_limit_percent",
    "Current speed limit percentage",
)

emergency_stop_active = Gauge(
    "rvr_emergency_stop_active",
    "Whether emergency stop is currently active",
)

# Circuit breaker metrics
circuit_breaker_state_enum = Enum(
    "rvr_circuit_breaker_state",
    "Circuit breaker state",
    states=["closed", "open", "half_open"],
)

circuit_breaker_failures_total = Counter(
    "rvr_circuit_breaker_failures_total",
    "Number of circuit breaker failures",
)

circuit_breaker_successes_total = Counter(
    "rvr_circuit_breaker_successes_total",
    "Number of circuit breaker successes",
)

circuit_breaker_state_transitions_total = Counter(
    "rvr_circuit_breaker_state_transitions_total",
    "Number of circuit breaker state transitions",
    ["from_state", "to_state"],
)

# Event bus metrics
event_bus_events_total = Counter(
    "rvr_event_bus_events_total",
    "Total events published to event bus",
    ["event_type"],
)

event_bus_queue_depth = Gauge(
    "rvr_event_bus_queue_depth",
    "Number of events in event bus queue",
)

event_bus_dropped_events_total = Counter(
    "rvr_event_bus_dropped_events_total",
    "Number of events dropped due to backpressure",
)

# System info
system_info = Info(
    "rvr_system",
    "RVR system information",
)

# Battery metrics
battery_percentage = Gauge(
    "rvr_battery_percentage",
    "Battery charge percentage",
)

battery_voltage = Gauge(
    "rvr_battery_voltage_volts",
    "Battery voltage in volts",
)

# Motor metrics
motor_temperature_celsius = Gauge(
    "rvr_motor_temperature_celsius",
    "Motor temperature in Celsius",
    ["motor"],  # motor: left, right
)

# Error metrics
errors_total = Counter(
    "rvr_errors_total",
    "Total errors by type",
    ["error_type"],
)


# Utility functions for metrics updates
def record_command_execution(command_type: str, duration_seconds: float, success: bool):
    """Record command execution metrics.

    Args:
        command_type: Type of command executed
        duration_seconds: Execution duration
        success: Whether command succeeded
    """
    status = "success" if success else "error"
    command_total.labels(command_type=command_type, status=status).inc()
    command_duration_seconds.labels(command_type=command_type).observe(duration_seconds)


def record_command_timeout(command_type: str):
    """Record command timeout."""
    command_total.labels(command_type=command_type, status="timeout").inc()
    command_timeouts_total.labels(command_type=command_type).inc()


def update_connection_state(state: str):
    """Update connection state metric.

    Args:
        state: Connection state (disconnected, connecting, connected, reconnecting, error)
    """
    connection_state_enum.state(state)


def update_circuit_breaker_state(state: str):
    """Update circuit breaker state metric.

    Args:
        state: Circuit breaker state (closed, open, half_open)
    """
    circuit_breaker_state_enum.state(state)


def record_circuit_breaker_transition(from_state: str, to_state: str):
    """Record circuit breaker state transition."""
    circuit_breaker_state_transitions_total.labels(
        from_state=from_state, to_state=to_state
    ).inc()


def record_sensor_event(sensor: str, age_ms: Optional[float] = None):
    """Record sensor event.

    Args:
        sensor: Sensor name
        age_ms: Optional age of sensor data in milliseconds
    """
    sensor_events_total.labels(sensor=sensor).inc()
    if age_ms is not None:
        sensor_data_age_milliseconds.labels(sensor=sensor).observe(age_ms)


def update_system_info(firmware_version: str, mac_address: str):
    """Update system information metric."""
    system_info.info({
        "firmware_version": firmware_version,
        "mac_address": mac_address,
    })


def record_emergency_stop():
    """Record emergency stop activation."""
    emergency_stops_total.inc()
    emergency_stop_active.set(1)


def clear_emergency_stop():
    """Clear emergency stop metric."""
    emergency_stop_active.set(0)


def record_speed_limit_applied():
    """Record that speed limit was applied."""
    speed_limits_applied_total.inc()


def update_speed_limit(percent: float):
    """Update current speed limit."""
    speed_limit_percent.set(percent)


def record_error(error_type: str):
    """Record an error by type.

    Args:
        error_type: Type/class of error
    """
    errors_total.labels(error_type=error_type).inc()


def update_battery_metrics(percentage: Optional[float], voltage: Optional[float]):
    """Update battery metrics.

    Args:
        percentage: Battery percentage (0-100)
        voltage: Battery voltage
    """
    if percentage is not None:
        battery_percentage.set(percentage)
    if voltage is not None:
        battery_voltage.set(voltage)


def update_motor_temperature(motor: str, temperature: float):
    """Update motor temperature metric.

    Args:
        motor: Motor identifier ('left' or 'right')
        temperature: Temperature in Celsius
    """
    motor_temperature_celsius.labels(motor=motor).set(temperature)
