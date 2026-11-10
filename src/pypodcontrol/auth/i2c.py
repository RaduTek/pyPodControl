import errno
from abc import ABC, abstractmethod


class I2CNackError(Exception):
    """The I2C slave did not acknowledge (for the coprocessor: it is busy)"""


class I2CBus(ABC):
    """
    ### I2CBus

    Minimal I2C master interface used by the authentication coprocessor.

    Implementations must raise `I2CNackError` when the slave does not
    acknowledge its address, so the caller can retry.
    """

    @abstractmethod
    def write(self, address: int, data: bytes) -> None:
        """Write bytes to the 7-bit slave address"""

    @abstractmethod
    def write_read(self, address: int, data: bytes, length: int) -> bytes:
        """Write bytes, then read `length` bytes after a repeated start"""

    @abstractmethod
    def read(self, address: int, length: int) -> bytes:
        """Read `length` bytes, continuing after the previously read register"""

    def close(self) -> None:
        """Release the bus"""


class SMBus2Bus(I2CBus):
    """
    ### SMBus2Bus

    I2C bus through Linux i2c-dev using the `smbus2` package
    (`pip install pypodcontrol[i2c]`).
    """

    # EREMOTEIO is Linux-only (121)
    _NACK_ERRNOS = (errno.ENXIO, getattr(errno, "EREMOTEIO", 121), errno.EIO)

    def __init__(self, bus: int = 1) -> None:
        try:
            from smbus2 import SMBus, i2c_msg
        except ImportError as e:
            raise ImportError(
                "smbus2 is required for I2C access (pip install pypodcontrol[i2c])"
            ) from e

        self._msg = i2c_msg
        self._bus = SMBus(bus)

    def _transfer(self, *msgs) -> None:
        try:
            self._bus.i2c_rdwr(*msgs)
        except OSError as e:
            if e.errno in self._NACK_ERRNOS:
                raise I2CNackError(str(e)) from e
            raise

    def write(self, address: int, data: bytes) -> None:
        self._transfer(self._msg.write(address, list(data)))

    def write_read(self, address: int, data: bytes, length: int) -> bytes:
        # Separate transactions (stop in between, which the coprocessor spec
        # allows) rather than a repeated start, which the chip may not accept
        self._transfer(self._msg.write(address, list(data)))
        return self.read(address, length)

    def read(self, address: int, length: int) -> bytes:
        read = self._msg.read(address, length)
        self._transfer(read)
        return bytes(read)

    def close(self) -> None:
        self._bus.close()
