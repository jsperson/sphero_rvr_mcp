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

    # Parse header (minimum 6 bytes: flags, target, source, did, cid, seq)
    if len(packet) < 7:  # 6 header + 1 checksum
        raise ValueError(f"Packet too short: {len(packet)} bytes")

    flags = packet[0]
    target = packet[1]
    source = packet[2]
    did = packet[3]
    cid = packet[4]
    seq = packet[5]

    # Data is everything after header, before checksum
    data = packet[6:-1]

    return ParsedResponse(flags, did, cid, seq, data)
