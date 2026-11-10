import logging
import threading
import time

from ..errors import CoprocessorError
from .base import AuthenticationProvider
from .i2c import I2CBus, I2CNackError, SMBus2Bus

logger = logging.getLogger(__name__)

ADDRESS_RST_LOW = 0x10
"""7-bit address when RST is low during reset (write 0x20 / read 0x21)"""

ADDRESS_RST_HIGH = 0x11
"""7-bit address when RST is high during reset (write 0x22 / read 0x23)"""

# Register map (iPod Authentication Coprocessor 2.0C, table 4-1)
REG_DEVICE_VERSION = 0x00
REG_PROTOCOL_MAJOR = 0x02
REG_DEVICE_ID = 0x04
REG_ERROR_CODE = 0x05
REG_AUTH_CONTROL = 0x10
REG_SIGNATURE_LENGTH = 0x11
REG_SIGNATURE_DATA = 0x12
REG_CHALLENGE_LENGTH = 0x20
REG_CHALLENGE_DATA = 0x21
REG_CERTIFICATE_LENGTH = 0x30
REG_CERTIFICATE_DATA = 0x31  # page 1, readable as one continuous stream

DEVICE_VERSION = 0x05
MAX_SIGNATURE_LENGTH = 128
MAX_CHALLENGE_LENGTH = 128
MAX_CERTIFICATE_LENGTH = 1280

PROC_SIGN = 1
RESULT_SIGNATURE_GENERATED = 1
ERR_SET = 0x80

ERROR_CODES = {
    0x01: "Invalid register for read",
    0x02: "Invalid register for write",
    0x03: "Invalid signature length",
    0x04: "Invalid challenge length",
    0x05: "Invalid certificate length",
    0x06: "Internal error during signature generation",
    0x07: "Internal error during challenge generation",
    0x08: "Internal error during signature verification",
    0x09: "Internal error during certificate validation",
    0x0A: "Invalid process control",
    0x0B: "Process control out of sequence",
}

NACK_RETRY_DELAY = 0.0005
"""Wait before retrying after a NACK (spec: 500 us)"""


class CoprocessorAuthenticationProvider(AuthenticationProvider):
    """
    ### CoprocessorAuthenticationProvider

    Authentication using an Apple iPod Authentication Coprocessor 2.0C
    connected over I2C. Reads the accessory certificate and generates
    signatures with the chip, so stock iPods authenticate the accessory.
    """

    def __init__(
        self,
        bus: I2CBus | int = 1,
        address: int = ADDRESS_RST_LOW,
        busy_timeout: float = 1.0,
        process_timeout: float = 2.0,
    ) -> None:
        """
        Create a new coprocessor authentication provider

        - bus: An `I2CBus`, or a Linux i2c-dev bus number (requires smbus2)
        - address: 7-bit I2C address, 0x10 (RST low) or 0x11 (RST high)
        - busy_timeout: How long to retry while the chip NACKs, in seconds
        - process_timeout: How long to wait for a signature to finish, in seconds
        """

        self._bus = SMBus2Bus(bus) if isinstance(bus, int) else bus
        self.address = address
        self.busy_timeout = busy_timeout
        self.process_timeout = process_timeout

        self._lock = threading.RLock()
        self._info: tuple[tuple[int, int], int] | None = None
        self._certificate: bytes | None = None

    def close(self) -> None:
        """Release the I2C bus"""

        self._bus.close()

    def __enter__(self) -> "CoprocessorAuthenticationProvider":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # I2C access

    def _retry(self, operation):
        deadline = time.monotonic() + self.busy_timeout
        while True:
            try:
                return operation()
            except I2CNackError as e:
                if time.monotonic() >= deadline:
                    raise CoprocessorError(
                        f"Coprocessor stayed busy (I2C NACK: {e})"
                    ) from e
                time.sleep(NACK_RETRY_DELAY)

    def _read(self, register: int, length: int) -> bytes:
        data = self._retry(
            lambda: self._bus.write_read(self.address, bytes([register]), length)
        )
        if len(data) != length:
            raise CoprocessorError(f"Short read from register 0x{register:02X}")
        return data

    def _write(self, register: int, data: bytes) -> None:
        self._retry(lambda: self._bus.write(self.address, bytes([register]) + data))

    def _read_error(self) -> int:
        return self._read(REG_ERROR_CODE, 1)[0]

    # Chip information

    def _chip_info(self) -> tuple[tuple[int, int], int]:
        with self._lock:
            if self._info is None:
                version = self._read(REG_DEVICE_VERSION, 1)[0]
                if version != DEVICE_VERSION:
                    raise CoprocessorError(
                        f"Unsupported coprocessor device version 0x{version:02X} "
                        f"(expected 0x{DEVICE_VERSION:02X}, 2.0C)"
                    )

                proto = self._read(REG_PROTOCOL_MAJOR, 2)
                device_id = int.from_bytes(self._read(REG_DEVICE_ID, 4), "big")
                self._info = ((proto[0], proto[1]), device_id)
                logger.info(
                    "Coprocessor protocol %d.%d, device ID 0x%08X",
                    proto[0],
                    proto[1],
                    device_id,
                )

            return self._info

    @property
    def protocol_version(self) -> tuple[int, int]:
        return self._chip_info()[0]

    @property
    def device_id(self) -> int:
        return self._chip_info()[1]

    # Authentication

    def get_certificate(self) -> bytes:
        """Read and cache the accessory certificate from the chip"""

        with self._lock:
            if self._certificate is None:
                length = int.from_bytes(self._read(REG_CERTIFICATE_LENGTH, 2), "big")
                if not 0 < length <= MAX_CERTIFICATE_LENGTH:
                    raise CoprocessorError(
                        f"Invalid certificate length {length} reported by coprocessor"
                    )

                # Pages are one continuous stream; read in chunks of one page
                data = b""
                while len(data) < length:
                    count = min(128, length - len(data))
                    if not data:
                        data += self._read(REG_CERTIFICATE_DATA, count)
                    else:
                        data += self._retry(
                            lambda: self._bus.read(self.address, count)
                        )
                self._certificate = data

            return self._certificate

    def sign_challenge(self, challenge: bytes) -> bytes:
        """Have the chip sign the challenge and return the signature"""

        if not 0 < len(challenge) <= MAX_CHALLENGE_LENGTH:
            raise ValueError(
                f"Challenge must be 1 to {MAX_CHALLENGE_LENGTH} bytes, got {len(challenge)}"
            )

        with self._lock:
            self._write(
                REG_CHALLENGE_LENGTH,
                len(challenge).to_bytes(2, "big") + challenge,
            )
            self._write(
                REG_SIGNATURE_LENGTH, MAX_SIGNATURE_LENGTH.to_bytes(2, "big")
            )
            self._write(REG_AUTH_CONTROL, bytes([PROC_SIGN]))

            deadline = time.monotonic() + self.process_timeout
            while True:
                status = self._read(REG_AUTH_CONTROL, 1)[0]
                if status & ERR_SET:
                    code = self._read_error()
                    raise CoprocessorError(
                        "Signature generation failed: "
                        + ERROR_CODES.get(code, f"error 0x{code:02X}"),
                        code,
                    )

                if (status >> 4) & 0x07 == RESULT_SIGNATURE_GENERATED:
                    break

                if time.monotonic() >= deadline:
                    raise CoprocessorError("Timed out waiting for signature generation")

                time.sleep(NACK_RETRY_DELAY)

            length = int.from_bytes(self._read(REG_SIGNATURE_LENGTH, 2), "big")
            if not 0 < length <= MAX_SIGNATURE_LENGTH:
                raise CoprocessorError(f"Invalid signature length {length}")

            return self._read(REG_SIGNATURE_DATA, length)
