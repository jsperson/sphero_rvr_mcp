"""MCP tools for LED control."""

from ..services.led_service import LEDService


def register_led_tools(mcp, led_service: LEDService):
    """Register LED tools with MCP server.

    Args:
        mcp: FastMCP instance
        led_service: LED service instance
    """

    @mcp.tool()
    async def set_all_leds(red: int, green: int, blue: int) -> dict:
        """Set all LEDs to the same color.

        Args:
            red: Red component 0-255
            green: Green component 0-255
            blue: Blue component 0-255

        Returns:
            Result
        """
        return await led_service.set_all_leds(red, green, blue)

    @mcp.tool()
    async def set_led(led_group: str, red: int, green: int, blue: int) -> dict:
        """Set a specific LED group to a color.

        Args:
            led_group: LED group name (headlight_left, headlight_right, brakelight_left,
                       brakelight_right, status_indication_left, status_indication_right,
                       battery_door_front, battery_door_rear, power_button_front,
                       power_button_rear, undercarriage_white)
            red: Red component 0-255
            green: Green component 0-255
            blue: Blue component 0-255

        Returns:
            Result
        """
        return await led_service.set_led(led_group, red, green, blue)

    @mcp.tool()
    async def turn_leds_off() -> dict:
        """Turn off all LEDs.

        Returns:
            Result
        """
        return await led_service.turn_leds_off()
