# Sphero RVR MCP Server

An MCP (Model Context Protocol) server that enables Claude AI to control a [Sphero RVR](https://sphero.com/collections/rvr) robot. Run this on a Raspberry Pi connected to your RVR, and use Claude Code to drive, control LEDs, read sensors, and more.

## Features

- **Full RVR Control**: Movement, LEDs, sensors, battery monitoring, IR communication
- **Safety System**: Configurable speed limits, auto-stop timeout, emergency stop
- **Sensor Streaming**: Background streaming with cached data access
- **Natural Language Control**: Let Claude drive your robot with conversational commands

## Requirements

- Raspberry Pi 3 or newer (connected to Sphero RVR via serial)
- Python 3.10.19 (required for Sphero SDK compatibility)
- Sphero RVR with serial connection to Pi
- Internet connection (for Claude Code API access)

## Installation

### 1. Clone the Sphero SDK

The Sphero SDK is not available on PyPI and must be installed manually:

```bash
cd ~
git clone https://github.com/sphero-inc/sphero-sdk-raspberrypi-python.git
```

### 2. Install the MCP Server

**Option A: Install from PyPI** (recommended)

```bash
pip install sphero-rvr-mcp

# Add Sphero SDK to Python path (add to ~/.bashrc for persistence)
export PYTHONPATH="${PYTHONPATH}:${HOME}/sphero-sdk-raspberrypi-python"
```

**Option B: Install from source**

```bash
cd /path/to/sphero_development

# Install the package in development mode
pip install -e .

# Add Sphero SDK to Python path (add to ~/.bashrc for persistence)
export PYTHONPATH="${PYTHONPATH}:${HOME}/sphero-sdk-raspberrypi-python"
```

### 3. Verify Installation

Run the pre-flight check to verify everything is set up correctly:

```bash
sphero-rvr-mcp --check
```

This will verify:
- Python version (requires 3.10+)
- Sphero SDK is installed
- FastMCP is installed
- Serial port exists and is accessible
- Current configuration settings

### 4. Install Claude Code

```bash
# Install Node.js if not already installed
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install Claude Code
npm install -g @anthropic-ai/claude-code
```

### 5. Configure Claude Code

Create or edit `~/.claude.json` (replace `<your-home-dir>` with your home path, e.g., `/home/pi`):

```json
{
  "mcpServers": {
    "sphero-rvr": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "sphero_rvr_mcp"],
      "env": {
        "PYTHONPATH": "<your-home-dir>/sphero-sdk-raspberrypi-python"
      }
    }
  }
}
```

Or use the CLI:

```bash
claude mcp add sphero-rvr -c "python -m sphero_rvr_mcp"
```

## Configuration

Environment variables (optional):

| Variable | Default | Description |
|----------|---------|-------------|
| `RVR_SERIAL_PORT` | `/dev/ttyS0` | Serial port for RVR |
| `RVR_MAX_SPEED_PERCENT` | `50` | Default speed limit (0-100) |
| `RVR_COMMAND_TIMEOUT` | `5.0` | Auto-stop timeout in seconds |
| `RVR_SENSOR_INTERVAL` | `250` | Sensor streaming interval (ms) |

## Usage

### Start Claude Code

```bash
claude
```

### Example Commands

Once Claude Code is running with the MCP server connected:

```
You: Connect to the RVR

You: Drive forward slowly for 2 seconds then stop

You: Set all LEDs to blue

You: What's the battery level?

You: Start streaming the accelerometer and gyroscope sensors

You: Turn left 90 degrees

You: Emergency stop!
```

## Available Tools

### Connection (3 tools)
| Tool | Description |
|------|-------------|
| `connect` | Connect to RVR and wake it up |
| `disconnect` | Safely disconnect |
| `get_connection_status` | Get connection state, uptime, firmware |

### Movement (10 tools)
| Tool | Description |
|------|-------------|
| `drive_with_heading` | Drive at speed toward heading (0-359°) |
| `drive_tank` | Tank drive with left/right velocities (m/s) |
| `drive_rc` | RC-style with linear + yaw velocity |
| `drive_to_position` | Drive to X,Y coordinates |
| `stop` | Normal stop (optional deceleration) |
| `emergency_stop` | Immediate stop, blocks movement |
| `clear_emergency_stop` | Allow movement after e-stop |
| `reset_yaw` | Set current heading as 0° |
| `reset_locator` | Set current position as origin |

### LEDs (3 tools)
| Tool | Description |
|------|-------------|
| `set_all_leds` | Set all LEDs to RGB color |
| `set_led` | Set specific LED group to RGB |
| `turn_leds_off` | Turn off all LEDs |

LED groups: `headlight_left`, `headlight_right`, `brakelight_left`, `brakelight_right`, `status_indication_left`, `status_indication_right`, `battery_door_front`, `battery_door_rear`, `power_button_front`, `power_button_rear`, `undercarriage_white`

### Sensors (5 tools)
| Tool | Description |
|------|-------------|
| `start_sensor_streaming` | Start background sensor streaming |
| `stop_sensor_streaming` | Stop all streaming |
| `get_sensor_data` | Get cached sensor readings |
| `get_ambient_light` | Query light sensor directly |
| `get_color_detection` | Query color sensor directly |

Streamable sensors: `accelerometer`, `gyroscope`, `imu`, `locator`, `velocity`, `speed`, `quaternion`, `color_detection`, `ambient_light`, `encoders`, `core_time`

### Battery & System (3 tools)
| Tool | Description |
|------|-------------|
| `get_battery_status` | Battery percentage, voltage, state |
| `get_motor_temperatures` | Motor thermal status |
| `get_system_info` | MAC, firmware, uptime |

### Safety Controls (3 tools)
| Tool | Description |
|------|-------------|
| `get_safety_status` | Current safety settings |
| `set_speed_limit` | Set max speed (0-100%) |
| `set_command_timeout` | Set auto-stop timeout |

### IR Communication (3 tools)
| Tool | Description |
|------|-------------|
| `send_ir_message` | Send IR code (0-7) |
| `start_ir_broadcasting` | Start robot-to-robot IR |
| `stop_ir_broadcasting` | Stop IR broadcasting |

## Safety Features

### Speed Limiting
All movement commands are limited to a configurable percentage of max speed (default 50%). This prevents accidental high-speed collisions.

```
You: Set the speed limit to 25%
You: Now drive forward at full speed
# RVR will only go at 25% of max speed
```

### Command Timeout
If no movement command is received within the timeout period (default 5 seconds), the RVR automatically stops. This prevents runaway situations if connection is lost.

### Emergency Stop
Immediately stops all movement and blocks further motion until explicitly cleared.

```
You: Emergency stop!
# RVR stops immediately
# All movement commands will fail until:
You: Clear the emergency stop
```

## Troubleshooting

### "Failed to connect to RVR"
- Check serial connection: `ls /dev/ttyS0`
- Ensure RVR is powered on
- Verify baud rate (default 115200)

### "sphero_sdk not found"
- Add SDK to PYTHONPATH: `export PYTHONPATH="${PYTHONPATH}:/path/to/sphero-sdk-raspberrypi-python"`

### Slow response
- Raspberry Pi 3 may be slower than Pi 4/5
- Reduce sensor streaming frequency
- Close unnecessary applications

### RVR not responding to commands
- Check if emergency stop is active: `get_safety_status`
- Verify connection: `get_connection_status`
- Try disconnecting and reconnecting

## Project Structure

```
sphero_development/
├── pyproject.toml              # Package configuration
├── README.md                   # This file
├── LICENSE                     # MIT License
└── src/sphero_rvr_mcp/
    ├── __init__.py
    ├── __main__.py             # Entry point
    ├── config.py               # Configuration dataclasses
    ├── models.py               # Pydantic response models
    ├── rvr_manager.py          # Connection lifecycle
    ├── sensor_manager.py       # Sensor streaming
    ├── safety_controller.py    # Safety system
    └── server.py               # MCP server + tools
```

## License

MIT
