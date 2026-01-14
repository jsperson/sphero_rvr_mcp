# Migration Guide: v0.1.x → v0.2.0

This guide helps you migrate from the original Sphero RVR MCP Server (v0.1.x) to the rewritten v0.2.0 with production-grade architecture.

## Overview of Changes

v0.2.0 is a **complete rewrite** with:
- New modular architecture
- Command queue, circuit breaker, event bus
- Comprehensive observability
- Bug fixes (especially color sensor)
- Performance improvements

## For MCP Users (Most Common)

### ✅ No Changes Required!

If you're using the server via MCP (Claude Code, Claude Desktop, etc.), **no changes are needed**. The MCP tool interface is identical.

**All 29 MCP tools work exactly the same:**
- `connect`, `disconnect`, `get_connection_status`
- `drive_with_heading`, `drive_tank`, `drive_rc`, `stop`, `emergency_stop`, etc.
- `set_all_leds`, `set_led`, `turn_leds_off`
- `start_sensor_streaming`, `stop_sensor_streaming`, `get_sensor_data`
- `get_ambient_light`, `get_color_detection`
- `get_battery_status`, `get_system_info`
- `set_speed_limit`, `set_command_timeout`, `get_safety_status`
- `send_ir_message`, `start_ir_broadcasting`, `stop_ir_broadcasting`

### ✅ What You'll Notice

**Improvements:**
- ✅ Color detection now works (was returning all zeros)
- ✅ Faster connection (no 2-second delay)
- ✅ Better error messages
- ✅ No more silent failures

**Behavior Changes:**
- Default speed limit still 50% (configurable via `RVR_MAX_SPEED_PERCENT`)
- Default command timeout still 5s (configurable via `RVR_COMMAND_TIMEOUT`)

## For Direct API Users

If you were importing and using the server modules directly, you'll need to update your imports.

### Import Path Changes

**OLD (v0.1.x)**:
```python
from sphero_rvr_mcp.rvr_manager import RVRManager
from sphero_rvr_mcp.sensor_manager import SensorManager
from sphero_rvr_mcp.safety_controller import SafetyController
```

**NEW (v0.2.0)**:
```python
# Use the new API client
from sphero_rvr_mcp.api import RVRClient

# Or import specific components
from sphero_rvr_mcp.hardware.connection_manager import ConnectionManager
from sphero_rvr_mcp.hardware.sensor_stream_manager import SensorStreamManager
from sphero_rvr_mcp.hardware.safety_monitor import SafetyMonitor
from sphero_rvr_mcp.services.movement_service import MovementService
```

### Using the New API Client

**OLD (v0.1.x)**:
```python
import asyncio
from sphero_rvr_mcp.rvr_manager import RVRManager
from sphero_rvr_mcp.config import RVRConfig

async def main():
    config = RVRConfig()
    manager = RVRManager(config)

    await manager.connect()
    # Use manager...
    await manager.disconnect()

asyncio.run(main())
```

**NEW (v0.2.0)**:
```python
import asyncio
from sphero_rvr_mcp.api import RVRClient

async def main():
    client = RVRClient(log_level="INFO", log_format="console")

    await client.initialize()
    await client.connect()

    # LED control
    await client.set_all_leds(255, 0, 0)

    # Sensors
    color = await client.get_color_detection()
    battery = await client._sensor_service.get_battery_status()

    await client.shutdown()

asyncio.run(main())
```

### Module Organization Changes

**OLD Structure**:
```
src/sphero_rvr_mcp/
├── rvr_manager.py
├── sensor_manager.py
├── safety_controller.py
└── server.py
```

**NEW Structure**:
```
src/sphero_rvr_mcp/
├── api.py                  # NEW: Direct API client
├── server.py               # Rewritten
├── core/                   # NEW: Infrastructure
│   ├── command_queue.py
│   ├── circuit_breaker.py
│   ├── event_bus.py
│   └── state_manager.py
├── hardware/               # NEW: Hardware abstraction
│   ├── connection_manager.py
│   ├── sensor_stream_manager.py
│   └── safety_monitor.py
├── services/               # NEW: Application services
│   ├── connection_service.py
│   ├── movement_service.py
│   ├── sensor_service.py
│   ├── led_service.py
│   ├── safety_service.py
│   └── ir_service.py
└── tools/                  # NEW: MCP tool handlers
    ├── connection_tools.py
    ├── movement_tools.py
    ├── sensor_tools.py
    ├── led_tools.py
    ├── safety_tools.py
    └── ir_tools.py
```

## Environment Variables

### New Variables

These are **new** in v0.2.0:

```bash
# Connection
RVR_WAKE_TIMEOUT=5.0

# Performance
RVR_COMMAND_QUEUE_SIZE=100
RVR_SENSOR_CACHE_TTL=2.0

# Observability
RVR_LOG_LEVEL=INFO
RVR_LOG_FORMAT=json
RVR_METRICS_ENABLED=true
RVR_METRICS_PORT=9090

# Circuit Breaker
RVR_CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
RVR_CIRCUIT_BREAKER_TIMEOUT=30.0
```

### Existing Variables (Unchanged)

These work the same as before:

```bash
RVR_SERIAL_PORT=/dev/ttyS0
RVR_BAUD_RATE=115200
RVR_MAX_SPEED_PERCENT=50.0
RVR_COMMAND_TIMEOUT=5.0
```

### Renamed/Removed Variables

None! All existing variables still work.

## Dependencies

### New Dependencies

v0.2.0 adds these dependencies (installed automatically via pip):

```toml
structlog>=24.1.0           # Structured logging
prometheus-client>=0.20.0   # Metrics
tenacity>=8.2.0             # Retry logic
nest-asyncio>=1.6.0         # SDK compatibility (re-added)
```

### Update Your Installation

```bash
# If installed from PyPI
pip install --upgrade sphero-rvr-mcp

# If installed from source
cd sphero_rvr_mcp
git pull
pip install -e .
```

## Breaking Changes

### For MCP Users: None! 🎉

### For Direct API Users:

1. **Import paths have changed** - see "Import Path Changes" above
2. **RVRManager class removed** - use `RVRClient` instead
3. **SensorManager class removed** - use `SensorStreamManager` or `SensorService`
4. **SafetyController class removed** - use `SafetyMonitor` or `SafetyService`

### Internal APIs

If you were using internal methods (anything not documented in the README), these have likely changed significantly. Refer to the new ARCHITECTURE.md for the new design.

## Bug Fixes You'll Get

### 1. Color Detection Now Works! 🎨

**Problem (v0.1.x)**: Color sensor always returned zeros
```python
result = await get_color_detection()
# {"r": 0, "g": 0, "b": 0, "c": 0}  # Always zeros! ❌
```

**Fixed (v0.2.0)**: Correctly parses SDK response keys
```python
result = await client.get_color_detection()
# {"success": true, "r": 377, "g": 507, "b": 534, "c": 1255}  # Works! ✅
```

### 2. No More 2-Second Connection Delay

**Before (v0.1.x)**:
```python
await rvr.wake()
await asyncio.sleep(2)  # Always 2 seconds ❌
```

**After (v0.2.0)**:
```python
await rvr.wake()
await self._wait_for_ready(timeout=5.0)  # Event-driven, typically <500ms ✅
```

### 3. No More Silent Failures

**Before (v0.1.x)**:
```python
try:
    await operation()
except Exception:
    pass  # Silently fails ❌
```

**After (v0.2.0)**:
```python
try:
    await operation()
except SpecificError as e:
    logger.error("operation_failed", error=str(e))
    metrics.operation_failures.inc()
    return {"success": False, "error": str(e)}  # Reported ✅
```

## New Features

### 1. Direct API Client

```python
from sphero_rvr_mcp.api import RVRClient

client = RVRClient(log_level="INFO")
await client.initialize()
await client.connect()

# Use all features without MCP protocol
await client.set_all_leds(255, 0, 0)
color = await client.get_color_detection()
```

### 2. Prometheus Metrics

```bash
# Enable metrics (default: enabled)
RVR_METRICS_ENABLED=true
RVR_METRICS_PORT=9090
```

Access at: `http://raspberry-pi-ip:9090/metrics`

### 3. Structured Logging

```bash
# JSON format (machine-readable)
RVR_LOG_FORMAT=json

# Console format (human-readable)
RVR_LOG_FORMAT=console
```

### 4. Circuit Breaker

Automatically prevents infinite hangs when RVR is off:
- After 5 connection failures → Circuit OPEN
- Fails fast for 30 seconds
- Then tries again (HALF_OPEN)

## Testing Your Migration

### 1. Test Connection

```bash
# Via MCP
claude> connect to the RVR

# Direct API
python -c "
import asyncio
from sphero_rvr_mcp.api import RVRClient

async def test():
    client = RVRClient(log_level='INFO', log_format='console')
    await client.initialize()
    result = await client.connect()
    print(result)
    await client.shutdown()

asyncio.run(test())
"
```

### 2. Test Color Detection

```bash
# Via MCP
claude> What color is under the rover?

# Direct API
python -c "
import asyncio
from sphero_rvr_mcp.api import RVRClient

async def test():
    client = RVRClient(log_level='WARNING', log_format='console')
    await client.initialize()
    await client.connect()
    color = await client.get_color_detection()
    print(f'Color: {color}')
    await client.shutdown()

asyncio.run(test())
"
```

### 3. Test LED Control

```bash
# Via MCP
claude> Set the LEDs to blue

# Direct API
python -c "
import asyncio
from sphero_rvr_mcp.api import RVRClient

async def test():
    client = RVRClient()
    await client.initialize()
    await client.connect()
    await client.set_all_leds(0, 0, 255)  # Blue
    await asyncio.sleep(2)
    await client.shutdown()

asyncio.run(test())
"
```

## Rollback Plan

If you need to rollback to v0.1.x:

```bash
# Via PyPI
pip install sphero-rvr-mcp==0.1.2

# Via source
cd sphero_rvr_mcp
git checkout v0.1.2
pip install -e .
```

## Getting Help

If you encounter issues:

1. Check the [CHANGELOG.md](CHANGELOG.md) for known issues
2. Review [ARCHITECTURE.md](ARCHITECTURE.md) for design details
3. Check logs with `RVR_LOG_FORMAT=console` for debugging
4. File an issue: https://github.com/jsperson/sphero_rvr_mcp/issues

## Recommended Upgrade Path

1. **Read this migration guide** 📖
2. **Update via pip**: `pip install --upgrade sphero-rvr-mcp`
3. **Test connection**: Verify RVR connects successfully
4. **Test your workflows**: Run your typical commands
5. **Check logs**: Look for any warnings or errors
6. **Enjoy the improvements!** 🎉

## Summary

| What | v0.1.x | v0.2.0 | Action Required |
|------|--------|--------|-----------------|
| **MCP Users** | Works | Works better | None - just upgrade! |
| **Direct API Users** | Old classes | New API client | Update imports |
| **Environment Vars** | 4 variables | 14 variables (4 old + 10 new) | Optional - all have defaults |
| **Dependencies** | 2 packages | 6 packages | Auto-installed |
| **Color Detection** | Broken | Fixed ✅ | None |
| **Connection Speed** | 2s delay | Event-driven | None |
| **Error Handling** | Silent failures | All logged | None |
| **Observability** | None | Logs + Metrics | Optional configuration |

**Bottom line**: If you're using MCP, just upgrade and enjoy the improvements! 🚀
