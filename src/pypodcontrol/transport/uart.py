from time import sleep

from serial import Serial, SerialException

from ..errors import TransportError
from ..packet import SYNC_BYTE, encode_byte
from .base import Transport


class UARTTransport(Transport):
    """
    ### UARTTransport

    iAP over a serial port (30 pin connector UART, 3.3V TTL)
    """

    port: Serial

    read_timeout: float = 0.1
    """Read timeout of the reader thread, in seconds"""

    wake_delay: float = 0.02
    """Delay after the wake up sync byte, in seconds"""

    def __init__(self, port: str | Serial, baudrate: int = 19200) -> None:
        """
        Create a new UART transport

        - port: Serial port name (e.g. /dev/ttyUSB0), or an existing Serial instance
        - baudrate: Baud rate, used only when port is a name
        """

        super().__init__()

        if isinstance(port, str):
            self.port = Serial()
            self.port.port = port
            self.port.baudrate = baudrate
        else:
            self.port = port

    def wake(self) -> None:
        """Send a sync byte to wake up a sleeping iPod"""

        with self._write_lock:
            self._write(encode_byte(SYNC_BYTE))
            sleep(self.wake_delay)

    def _open(self) -> None:
        self.port.timeout = self.read_timeout

        if not self.port.is_open:
            try:
                self.port.open()
            except SerialException as e:
                raise TransportError(f"Failed to open {self.port.port}: {e}") from e

    def _close(self) -> None:
        self.port.close()

    def _read_chunk(self) -> bytes:
        return self.port.read(self.port.in_waiting or 1)

    def _write_frame(self, frame: bytes) -> None:
        self._write(encode_byte(SYNC_BYTE) + frame)

    def _write(self, data: bytes) -> None:
        try:
            written = self.port.write(data)
        except SerialException as e:
            raise TransportError(f"Failed to write to {self.port.port}: {e}") from e

        if written is not None and written != len(data):
            raise TransportError("Packet data was not sent.")
