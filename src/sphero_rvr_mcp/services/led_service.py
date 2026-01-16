"""LED control service."""

from sphero_sdk import RvrLedGroups

from ..core.command_queue import CommandQueue
from ..hardware.connection_manager import ConnectionManager
from ..observability.logging import get_logger

logger = get_logger(__name__)

# LED group name to RvrLedGroups enum mapping
LED_GROUPS = {
    "headlight_left": RvrLedGroups.headlight_left,
    "headlight_right": RvrLedGroups.headlight_right,
    "battery_door_front": RvrLedGroups.battery_door_front,
    "battery_door_rear": RvrLedGroups.battery_door_rear,
    "power_button_front": RvrLedGroups.power_button_front,
    "power_button_rear": RvrLedGroups.power_button_rear,
    "brakelight_left": RvrLedGroups.brakelight_left,
    "brakelight_right": RvrLedGroups.brakelight_right,
    "undercarriage_white": RvrLedGroups.undercarriage_white,
    "status_indication_left": RvrLedGroups.status_indication_left,
    "status_indication_right": RvrLedGroups.status_indication_right,
    "all": RvrLedGroups.all_lights,
}


class LEDService:
    """LED control operations."""

    def __init__(
        self,
        connection_manager: ConnectionManager,
        command_queue: CommandQueue,
    ):
        """Initialize LED service.

        Args:
            connection_manager: Connection manager
            command_queue: Command queue
        """
        self._connection_manager = connection_manager
        self._command_queue = command_queue

    async def set_all_leds(self, red: int, green: int, blue: int) -> dict:
        """Set all LEDs to same color.

        Args:
            red: Red value 0-255
            green: Green value 0-255
            blue: Blue value 0-255

        Returns:
            Result
        """
        try:
            await self._connection_manager.ensure_connected()

            # Clamp values
            r = max(0, min(255, red))
            g = max(0, min(255, green))
            b = max(0, min(255, blue))

            async def led_command():
                await self._connection_manager.rvr.led_control.set_all_leds_rgb(
                    red=r,
                    green=g,
                    blue=b,
                )

            await self._command_queue.submit(
                led_command, timeout=0.5
            )

            return {"success": True, "red": r, "green": g, "blue": b}

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_led(self, led_group: str, red: int, green: int, blue: int) -> dict:
        """Set specific LED group.

        Args:
            led_group: LED group name
            red: Red value 0-255
            green: Green value 0-255
            blue: Blue value 0-255

        Returns:
            Result
        """
        try:
            await self._connection_manager.ensure_connected()

            # Get LED mask
            led_mask = LED_GROUPS.get(led_group.lower())
            if led_mask is None:
                return {
                    "success": False,
                    "error": f"Unknown LED group: {led_group}. Valid groups: {list(LED_GROUPS.keys())}",
                }

            # Clamp values
            r = max(0, min(255, red))
            g = max(0, min(255, green))
            b = max(0, min(255, blue))

            async def led_command():
                # Use set_multiple_leds_with_rgb with the LED group enum
                await self._connection_manager.rvr.led_control.set_multiple_leds_with_rgb(
                    leds=[led_mask],
                    colors=[r, g, b],
                )

            await self._command_queue.submit(
                led_command, timeout=0.5
            )

            return {
                "success": True,
                "led_group": led_group,
                "red": r,
                "green": g,
                "blue": b,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    async def turn_leds_off(self) -> dict:
        """Turn off all LEDs.

        Returns:
            Result
        """
        return await self.set_all_leds(0, 0, 0)
