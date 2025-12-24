"""Pydantic models for MCP tool responses."""

from typing import Optional
from pydantic import BaseModel, Field


# Connection models
class ConnectionResult(BaseModel):
    """Result of connect/disconnect operations."""
    success: bool
    message: str


class ConnectionStatus(BaseModel):
    """Current connection status."""
    connected: bool
    uptime_seconds: Optional[float] = None
    firmware_version: Optional[str] = None
    mac_address: Optional[str] = None


# Movement models
class DriveResult(BaseModel):
    """Result of drive commands."""
    success: bool
    actual_speed: Optional[int] = None
    actual_left_velocity: Optional[float] = None
    actual_right_velocity: Optional[float] = None
    limited: bool = False
    error: Optional[str] = None


class StopResult(BaseModel):
    """Result of stop commands."""
    success: bool
    message: Optional[str] = None


# LED models
class LedResult(BaseModel):
    """Result of LED commands."""
    success: bool
    error: Optional[str] = None


# Sensor models
class AccelerometerData(BaseModel):
    """Accelerometer sensor data."""
    x: float = Field(description="X-axis acceleration in g")
    y: float = Field(description="Y-axis acceleration in g")
    z: float = Field(description="Z-axis acceleration in g")


class GyroscopeData(BaseModel):
    """Gyroscope sensor data."""
    x: float = Field(description="X-axis angular velocity in deg/s")
    y: float = Field(description="Y-axis angular velocity in deg/s")
    z: float = Field(description="Z-axis angular velocity in deg/s")


class LocatorData(BaseModel):
    """Locator position data."""
    x: float = Field(description="X position in meters")
    y: float = Field(description="Y position in meters")


class VelocityData(BaseModel):
    """Velocity data."""
    x: float = Field(description="X velocity in m/s")
    y: float = Field(description="Y velocity in m/s")


class QuaternionData(BaseModel):
    """Quaternion orientation data."""
    w: float
    x: float
    y: float
    z: float


class ImuData(BaseModel):
    """IMU data (pitch, roll, yaw)."""
    pitch: float = Field(description="Pitch angle in degrees")
    roll: float = Field(description="Roll angle in degrees")
    yaw: float = Field(description="Yaw angle in degrees")


class ColorDetectionData(BaseModel):
    """Color sensor detection data."""
    r: int = Field(description="Red component 0-255")
    g: int = Field(description="Green component 0-255")
    b: int = Field(description="Blue component 0-255")
    confidence: float = Field(description="Detection confidence 0-1")


class AmbientLightData(BaseModel):
    """Ambient light sensor data."""
    value: float = Field(description="Light level in lux")


class SensorReading(BaseModel):
    """Generic sensor reading with metadata."""
    sensor_name: str
    data: dict
    timestamp: float
    age_ms: float = Field(description="Age of reading in milliseconds")


class SensorDataResult(BaseModel):
    """Result of sensor data query."""
    success: bool
    sensors: dict = Field(default_factory=dict)
    error: Optional[str] = None


class StreamingResult(BaseModel):
    """Result of streaming start/stop."""
    success: bool
    sensors_enabled: list[str] = Field(default_factory=list)
    error: Optional[str] = None


# Battery models
class BatteryStatus(BaseModel):
    """Battery status information."""
    percentage: int = Field(description="Battery percentage 0-100")
    voltage: float = Field(description="Battery voltage in volts")
    state: str = Field(description="Battery state: charging, discharging, full, etc.")


class MotorTemperatures(BaseModel):
    """Motor thermal status."""
    left_temp: float = Field(description="Left motor temperature in Celsius")
    right_temp: float = Field(description="Right motor temperature in Celsius")
    left_status: str = Field(description="Left motor thermal status")
    right_status: str = Field(description="Right motor thermal status")


# System models
class SystemInfo(BaseModel):
    """RVR system information."""
    mac_address: str
    firmware_version: str
    hardware_version: Optional[str] = None
    uptime_seconds: float


class SafetyStatus(BaseModel):
    """Safety system status."""
    speed_limit_percent: float = Field(description="Current speed limit 0-100")
    timeout_enabled: bool
    timeout_seconds: float
    last_command_age_ms: Optional[float] = None
    emergency_stopped: bool = False
    collision_detection_enabled: bool = True


# IR models
class IrResult(BaseModel):
    """Result of IR operations."""
    success: bool
    error: Optional[str] = None
