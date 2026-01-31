"""RVR packet building - minimal implementation for direct serial."""

import struct

# Protocol constants
SOP = 0x8D
EOP = 0xD8
ESC = 0xAB
ESC_SOP = 0x05
ESC_EOP = 0x50
ESC_ESC = 0x23

# Flags
FLAG_IS_RESPONSE = 0x01
FLAG_REQUEST_RESPONSE = 0x02
FLAG_REQUEST_ERROR_ONLY = 0x04
FLAG_IS_ACTIVITY = 0x08
FLAG_HAS_TARGET = 0x10
FLAG_HAS_SOURCE = 0x20

# Device IDs
DID_SYSTEM_INFO = 0x11
DID_POWER = 0x13
DID_DRIVE = 0x16
DID_SENSOR = 0x18
DID_IO = 0x1A

# Targets
TARGET_MCU = 0x02  # Drive, sensors
TARGET_BT = 0x01   # LEDs, Bluetooth
SOURCE_HOST = 0x00


def checksum(data: bytes) -> int:
    return (sum(data) & 0xFF) ^ 0xFF


def escape_buffer(data: bytes) -> bytes:
    result = bytearray()
    for b in data:
        if b == SOP:
            result.extend([ESC, ESC_SOP])
        elif b == EOP:
            result.extend([ESC, ESC_EOP])
        elif b == ESC:
            result.extend([ESC, ESC_ESC])
        else:
            result.append(b)
    return bytes(result)


def unescape_buffer(data: bytes) -> bytes:
    """Unescape RVR packet data."""
    result = bytearray()
    i = 0
    while i < len(data):
        if data[i] == ESC and i + 1 < len(data):
            next_byte = data[i + 1]
            if next_byte == ESC_SOP:
                result.append(SOP)
            elif next_byte == ESC_EOP:
                result.append(EOP)
            elif next_byte == ESC_ESC:
                result.append(ESC)
            else:
                raise ValueError(f"Invalid escape sequence: {next_byte:02x}")
            i += 2
        else:
            result.append(data[i])
            i += 1
    return bytes(result)


_seq = 0

def next_seq() -> int:
    global _seq
    _seq = (_seq + 1) & 0xFF
    return _seq


def build_packet(did: int, cid: int, target: int, data: bytes = b"",
                 request_response: bool = False) -> bytes:
    """Build a complete packet ready to send."""
    flags = FLAG_HAS_TARGET | FLAG_HAS_SOURCE
    if request_response:
        flags |= FLAG_REQUEST_RESPONSE

    seq = next_seq()
    header = bytes([flags, target, SOURCE_HOST, did, cid, seq])
    content = header + data
    content_with_chk = content + bytes([checksum(content)])

    return bytes([SOP]) + escape_buffer(content_with_chk) + bytes([EOP])


def get_packet_header(packet: bytes) -> tuple:
    """Extract (did, cid, seq) from a built packet.

    This is useful for matching responses to requests when using
    the dispatcher pattern.

    Args:
        packet: Complete packet bytes (with SOP/EOP)

    Returns:
        Tuple of (did, cid, seq)

    Raises:
        ValueError: If packet is malformed
    """
    if len(packet) < 2:
        raise ValueError("Packet too short")

    if packet[0] != SOP:
        raise ValueError(f"Invalid SOP: {packet[0]:#x}")

    # Find EOP
    try:
        eop_idx = packet.index(EOP, 1)
    except ValueError:
        raise ValueError("No EOP found")

    # Unescape the content
    escaped_content = packet[1:eop_idx]
    content = unescape_buffer(escaped_content)

    # Content format: flags, target, source, did, cid, seq, [data...], checksum
    # Or simplified: flags, did, cid, seq, [data...], checksum (no target/source)

    if len(content) < 5:
        raise ValueError(f"Content too short: {len(content)} bytes")

    flags = content[0]

    # Check if packet has target/source fields
    if flags & FLAG_HAS_TARGET:
        # Full format: flags, target, source, did, cid, seq
        if len(content) < 7:
            raise ValueError(f"Content too short for full packet: {len(content)} bytes")
        did = content[3]
        cid = content[4]
        seq = content[5]
    else:
        # Simplified format: flags, did, cid, seq
        did = content[1]
        cid = content[2]
        seq = content[3]

    return (did, cid, seq)


class ParsedResponse:
    """Parsed RVR response packet."""
    def __init__(self, flags: int, did: int, cid: int, seq: int, data: bytes):
        self.flags = flags
        self.did = did
        self.cid = cid
        self.seq = seq
        self.data = data

    @property
    def is_response(self) -> bool:
        return bool(self.flags & FLAG_IS_RESPONSE)

    @property
    def error_code(self) -> int:
        """Return error code if present (first byte of data), else 0."""
        if len(self.data) > 0 and not self.is_response:
            return self.data[0]
        return 0


def parse_response(buffer: bytes) -> ParsedResponse:
    """Parse a response packet from RVR.

    Args:
        buffer: Raw bytes including SOP and EOP

    Returns:
        ParsedResponse with extracted data

    Raises:
        ValueError: If packet is malformed or checksum fails
    """
    # Find SOP and EOP
    try:
        start_idx = buffer.index(SOP)
    except ValueError:
        raise ValueError("No SOP (0x8D) found in buffer")

    try:
        end_idx = buffer.index(EOP, start_idx)
    except ValueError:
        raise ValueError("No EOP (0xD8) found after SOP")

    # Extract packet (without SOP/EOP)
    escaped_packet = buffer[start_idx + 1:end_idx]

    # Unescape
    packet = unescape_buffer(escaped_packet)

    # Verify checksum (last byte)
    calculated_checksum = sum(packet) & 0xFF
    if calculated_checksum != 0xFF:
        raise ValueError(f"Bad checksum: {calculated_checksum:02x} (expected 0xFF)")

    # Minimum packet: flags + did + cid + seq + checksum = 5 bytes
    if len(packet) < 5:
        raise ValueError(f"Packet too short: {len(packet)} bytes")

    # Parse header dynamically based on flags (like SDK does)
    idx = 0
    flags = packet[idx]
    idx += 1

    # Skip target if present
    if flags & FLAG_HAS_TARGET:
        if idx >= len(packet) - 1:
            raise ValueError("Packet too short for target field")
        idx += 1  # target byte

    # Skip source if present
    if flags & FLAG_HAS_SOURCE:
        if idx >= len(packet) - 1:
            raise ValueError("Packet too short for source field")
        idx += 1  # source byte

    # Now read did, cid, seq
    if idx + 3 > len(packet) - 1:
        raise ValueError(f"Packet too short for did/cid/seq: need {idx+3}, have {len(packet)-1}")

    did = packet[idx]
    cid = packet[idx + 1]
    seq = packet[idx + 2]
    idx += 3

    # If response, skip error byte
    if flags & FLAG_IS_RESPONSE:
        if idx >= len(packet) - 1:
            raise ValueError("Packet too short for error field")
        idx += 1  # error byte

    # Data is everything after header, before checksum
    data = packet[idx:-1]

    return ParsedResponse(flags, did, cid, seq, data)
