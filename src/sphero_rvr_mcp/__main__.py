"""Entry point for Sphero RVR MCP Server."""

import argparse
import asyncio
import os
import signal
import sys

from . import __version__


def check_environment():
    """Run pre-flight checks for Sphero RVR MCP server."""
    print(f"Sphero RVR MCP Server v{__version__}")
    print("=" * 50)
    print("\nRunning pre-flight checks...\n")

    all_passed = True

    # Check 1: Python version
    py_version = sys.version_info
    if py_version >= (3, 10):
        print(f"[OK] Python version: {py_version.major}.{py_version.minor}.{py_version.micro}")
    else:
        print(f"[FAIL] Python version: {py_version.major}.{py_version.minor}.{py_version.micro} (requires >= 3.10)")
        all_passed = False

    # Check 2: Sphero SDK
    try:
        import sphero_sdk
        print("[OK] Sphero SDK: installed")
    except ImportError:
        print("[FAIL] Sphero SDK: not installed")
        print("       Install from: https://github.com/sphero-inc/sphero-sdk-raspberrypi-python")
        all_passed = False

    # Check 3: FastMCP
    try:
        import fastmcp
        print("[OK] FastMCP: installed")
    except ImportError:
        print("[FAIL] FastMCP: not installed (run: pip install fastmcp)")
        all_passed = False

    # Check 4: Serial port
    serial_port = os.environ.get("RVR_SERIAL_PORT", "/dev/ttyS0")
    if os.path.exists(serial_port):
        print(f"[OK] Serial port: {serial_port} exists")
        # Check if readable
        if os.access(serial_port, os.R_OK | os.W_OK):
            print(f"[OK] Serial port: {serial_port} is accessible")
        else:
            print(f"[WARN] Serial port: {serial_port} may not be accessible (check permissions)")
            print("       Try: sudo usermod -a -G dialout $USER")
    else:
        print(f"[WARN] Serial port: {serial_port} does not exist")
        print("       Set RVR_SERIAL_PORT environment variable if using a different port")

    # Check 5: Show configuration
    print("\n" + "=" * 50)
    print("Current Configuration (from environment):")
    print("=" * 50)
    print(f"  RVR_SERIAL_PORT:      {os.environ.get('RVR_SERIAL_PORT', '/dev/ttyS0 (default)')}")
    print(f"  RVR_BAUD_RATE:        {os.environ.get('RVR_BAUD_RATE', '115200 (default)')}")
    print(f"  RVR_MAX_SPEED_PERCENT:{os.environ.get('RVR_MAX_SPEED_PERCENT', '50 (default)')}")
    print(f"  RVR_COMMAND_TIMEOUT:  {os.environ.get('RVR_COMMAND_TIMEOUT', '5.0 (default)')} seconds")
    print(f"  RVR_SENSOR_INTERVAL:  {os.environ.get('RVR_SENSOR_INTERVAL', '250 (default)')} ms")

    print("\n" + "=" * 50)
    if all_passed:
        print("All checks passed! Ready to run.")
        return 0
    else:
        print("Some checks failed. Please resolve the issues above.")
        return 1


async def cleanup():
    """Clean up on shutdown."""
    from .server import _rvr_manager, _sensor_manager

    if _sensor_manager is not None:
        try:
            await _sensor_manager.stop_streaming()
        except Exception:
            pass

    if _rvr_manager is not None:
        try:
            await _rvr_manager.disconnect()
        except Exception:
            pass


def handle_signal(sig, frame):
    """Handle shutdown signals."""
    print("\nShutting down Sphero RVR MCP server...", file=sys.stderr)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(cleanup())
    sys.exit(0)


def main():
    """Run the MCP server."""
    parser = argparse.ArgumentParser(
        description="Sphero RVR MCP Server - Control Sphero RVR with Claude AI"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run pre-flight checks and exit"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )

    args = parser.parse_args()

    if args.check:
        sys.exit(check_environment())

    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Get and run the server
    from .server import get_server
    server = get_server()
    server.run()


if __name__ == "__main__":
    main()
