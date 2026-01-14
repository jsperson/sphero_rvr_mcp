"""MCP tools for sensor operations."""

from typing import List, Optional

from ..services.sensor_service import SensorService


def register_sensor_tools(mcp, sensor_service: SensorService):
    """Register sensor tools with MCP server.

    Args:
        mcp: FastMCP instance
        sensor_service: Sensor service instance
    """

    @mcp.tool()
    async def start_sensor_streaming(sensors: List[str], interval_ms: int = 250) -> dict:
        """Start streaming sensor data in the background.

        Args:
            sensors: List of sensors to stream. Options: accelerometer, gyroscope,
                     imu, locator, velocity, speed, quaternion, color_detection,
                     ambient_light, encoders, core_time
            interval_ms: Streaming interval in milliseconds (min 50)

        Returns:
            Result with list of enabled sensors
        """
        return await sensor_service.start_sensor_streaming(sensors, interval_ms)

    @mcp.tool()
    async def stop_sensor_streaming() -> dict:
        """Stop all sensor streaming.

        Returns:
            Result
        """
        return await sensor_service.stop_sensor_streaming()

    @mcp.tool()
    async def get_sensor_data(sensors: Optional[List[str]] = None) -> dict:
        """Get current sensor data from streaming cache.

        Args:
            sensors: Specific sensors to get, or None for all streaming sensors

        Returns:
            Sensor data with timestamps
        """
        return await sensor_service.get_sensor_data(sensors)

    @mcp.tool()
    async def get_ambient_light() -> dict:
        """Query ambient light sensor directly (not from streaming cache).

        Returns:
            Ambient light value
        """
        return await sensor_service.get_ambient_light()

    @mcp.tool()
    async def enable_color_detection(enabled: bool = True) -> dict:
        """Enable or disable the color sensor's illumination LED.

        Must be enabled before color detection will return valid readings.

        Args:
            enabled: True to enable, False to disable

        Returns:
            Result
        """
        return await sensor_service.enable_color_detection(enabled)

    @mcp.tool()
    async def get_color_detection(stabilization_ms: int = 50) -> dict:
        """Query color sensor directly (not from streaming cache).

        Automatically enables the illumination LED, reads the color, then disables the LED.

        Args:
            stabilization_ms: LED stabilization time in milliseconds (default 50)

        Returns:
            Color values (R, G, B, C)
        """
        return await sensor_service.get_color_detection(stabilization_ms)

    @mcp.tool()
    async def get_battery_status() -> dict:
        """Get battery status.

        Returns:
            Battery percentage, voltage, and state
        """
        return await sensor_service.get_battery_status()
