import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

START_BYTE = 0x55
"""Start of packet byte"""

SYNC_BYTE = 0xFF
"""Sync byte, sent before the start byte on UART"""

MAX_SMALL_PAYLOAD = 0xFC
"""Largest payload that fits a 1 byte length field"""

MAX_PAYLOAD = 0xFFFA
"""Largest payload that fits a 3 byte length field"""


def encode_byte(value: int, signed: bool = False) -> bytes:
    """Encode a byte (8 bits)"""

    return value.to_bytes(length=1, byteorder="big", signed=signed)


def encode_short(value: int, signed: bool = False) -> bytes:
    """Encode a short integer (16 bits)"""

    return value.to_bytes(length=2, byteorder="big", signed=signed)


def encode_int(value: int, signed: bool = False) -> bytes:
    """Encode a integer (32 bits)"""

    return value.to_bytes(length=4, byteorder="big", signed=signed)


def encode_long(value: int, signed: bool = False) -> bytes:
    """Encode a long integer (64 bits)"""

    return value.to_bytes(length=8, byteorder="big", signed=signed)


def checksum(data: bytes) -> int:
    """Checksum of length and payload bytes, makes their sum 0 (mod 256)"""

    return (-sum(data)) & 0xFF


def encode_length(length: int) -> bytes:
    """Encode the length field in its 1 byte or 3 byte form"""

    if length <= MAX_SMALL_PAYLOAD:
        return encode_byte(length)

    if length <= MAX_PAYLOAD:
        return b"\x00" + encode_short(length)

    raise ValueError(f"Payload too large: {length} bytes")


def encode_frame(payload: bytes) -> bytes:
    """Encode a payload into a packet frame (start byte, length, payload, checksum)"""

    body = encode_length(len(payload)) + payload

    return encode_byte(START_BYTE) + body + encode_byte(checksum(body))


@dataclass(frozen=True)
class Packet:
    """
    ### Packet

    A decoded iAP command packet
    """

    lingo_id: int
    command_id: int
    data: bytes = b""
    transaction_id: int | None = None

    def to_payload(self, extended_command: bool = False) -> bytes:
        """Encode the packet payload (lingo ID, command ID, transaction ID, data)"""

        payload = encode_byte(self.lingo_id)
        payload += (
            encode_short(self.command_id)
            if extended_command
            else encode_byte(self.command_id)
        )

        if self.transaction_id is not None:
            payload += encode_short(self.transaction_id)

        return payload + self.data

    @staticmethod
    def from_payload(
        payload: bytes,
        extended_command: bool = False,
        has_transaction_id: bool = False,
    ) -> "Packet":
        """Decode a packet payload"""

        command_size = 2 if extended_command else 1
        header_size = 1 + command_size + (2 if has_transaction_id else 0)

        if len(payload) < header_size:
            raise ValueError(f"Payload too short: {payload.hex(' ')}")

        lingo_id = payload[0]
        command_id = int.from_bytes(payload[1 : 1 + command_size], "big")

        transaction_id = None
        if has_transaction_id:
            transaction_id = int.from_bytes(
                payload[1 + command_size : header_size], "big"
            )

        return Packet(lingo_id, command_id, payload[header_size:], transaction_id)


class PacketParser:
    """
    ### PacketParser

    Incremental parser, extracts packet payloads from a byte stream
    """

    def __init__(self) -> None:
        self.buffer = bytearray()

    @property
    def in_packet(self) -> bool:
        """Whether a partial packet is buffered"""

        return len(self.buffer) > 0

    def reset(self) -> None:
        """Discard any partially received packet"""

        self.buffer.clear()

    def feed(self, data: bytes) -> list[bytes]:
        """Feed received bytes, returns the payloads of all completed packets"""

        self.buffer += data
        payloads = []

        while True:
            # Skip sync bytes, padding and garbage until the start byte
            start = self.buffer.find(START_BYTE)
            if start < 0:
                self.buffer.clear()
                break
            del self.buffer[:start]

            if len(self.buffer) < 2:
                break

            if self.buffer[1] == 0x00:
                if len(self.buffer) < 4:
                    break
                length = int.from_bytes(self.buffer[2:4], "big")
                header_size = 4

                if not MAX_SMALL_PAYLOAD < length <= MAX_PAYLOAD:
                    # Not a valid large packet, resync
                    del self.buffer[:1]
                    continue
            else:
                length = self.buffer[1]
                header_size = 2

            frame_size = header_size + length + 1
            if len(self.buffer) < frame_size:
                break

            body = bytes(self.buffer[1 : frame_size - 1])
            expected = self.buffer[frame_size - 1]

            if checksum(body) != expected:
                logger.warning(
                    "Dropping packet with bad checksum: %s",
                    bytes(self.buffer[:frame_size]).hex(" "),
                )
                # Resync from the byte after this start byte
                del self.buffer[:1]
                continue

            payloads.append(bytes(self.buffer[header_size : frame_size - 1]))
            del self.buffer[:frame_size]

        return payloads
