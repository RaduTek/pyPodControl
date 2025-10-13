from serial import Serial


class iAPBase:
    """
    ### iAPBase

    Implements the basic communication with iPod (packet format, checksum, reply)
    """

    packet_header = b"\xff\x55"

    port: Serial

    def __init__(self, port: str | Serial, baudrate: int = 19200) -> None:
        """
        Create a new iAPBase instance, with the given serial port
        """
        if isinstance(port, str):
            self.port = Serial(port, baudrate)
        else:
            self.port = port

        if not self.port.is_open:
            self.port.open()

    def send_packet(self, data: bytes) -> None:
        """
        Sends the packet data to the iPod
        """
        if self.port.write(data) == None:
            raise RuntimeError("Packet data was not sent.")

    def send_command(self, lingo_id: int, command_id: int, command_data: bytes) -> None:
        """
        Send a command to the iPod
        """
        data = iAPBase.encode_command(lingo_id, command_id, command_data)

        self.send_packet(data)

    @staticmethod
    def encode_byte(value: int, signed: bool = False) -> bytes:
        """Encode a byte (8 bits)"""

        return value.to_bytes(1, signed=signed)

    @staticmethod
    def encode_short(value: int, signed: bool = False) -> bytes:
        """Encode a short integer (16 bits)"""

        return value.to_bytes(2, signed=signed)

    @staticmethod
    def encode_int(value: int, signed: bool = False) -> bytes:
        """Encode a integer (32 bits)"""

        return value.to_bytes(4, signed=signed)

    @staticmethod
    def encode_long(value: int, signed: bool = False) -> bytes:
        """Encode a long integer (64 bits)"""

        return value.to_bytes(8, signed=signed)

    @staticmethod
    def get_checksum(bytes: bytes) -> bytes:
        """Get checksum of payload"""

        checksum = 0x100 - (sum(bytes) & 0xFF)
        return iAPBase.encode_byte(checksum)

    @staticmethod
    def encode_small_packet(data: bytes) -> bytes:
        """Encode a small packet (len(data) <= 255)"""

        length = iAPBase.encode_byte(len(data))
        payload = length + data
        checksum = iAPBase.get_checksum(payload)

        return iAPBase.packet_header + payload + checksum

    @staticmethod
    def encode_large_packet(data: bytes) -> bytes:
        """Encode a large packet (len(data) > 255)"""

        length = b"\x00" + iAPBase.encode_short(len(data))
        payload = length + data
        checksum = iAPBase.get_checksum(payload)

        return iAPBase.packet_header + payload + checksum

    @staticmethod
    def encode_packet(data: bytes) -> bytes:
        """Encode a packet in the appropriate format"""

        if len(data) > 255:
            return iAPBase.encode_large_packet(data)
        else:
            return iAPBase.encode_small_packet(data)

    @staticmethod
    def encode_command(
        lingo_id: int, command_id: int, command_data: bytes = b""
    ) -> bytes:
        """Encode a command packet"""

        lingo_id_b = iAPBase.encode_byte(lingo_id)
        command_id_b = iAPBase.encode_byte(command_id)

        payload = lingo_id_b + command_id_b + command_data

        return iAPBase.encode_packet(payload)
