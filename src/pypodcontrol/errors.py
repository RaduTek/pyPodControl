class iAPError(Exception):
    """Base class for all pyPodControl errors"""


class TransportError(iAPError):
    """Transport failed to open, read or write"""


class iAPTimeoutError(iAPError, TimeoutError):
    """No response was received from the iPod within the timeout period"""


class iAPIdentificationError(iAPError):
    """Identification with the iPod failed"""


class AudioError(iAPError):
    """Routing the iPod's digital audio failed (missing backend, no source, ...)"""


class iAPAckError(iAPError):
    """iPod acknowledged a command with a non-success status"""

    status: int
    """ACK status code returned by the iPod"""

    command: str
    """Name of the acknowledged command"""

    def __init__(self, status: int, command: str) -> None:
        self.status = status
        self.command = command

        # Imported lazily to avoid a circular import (general imports from here)
        from .lingo.general import General

        description = General.ACK_STATUSES.get(status)
        suffix = f" ({description})" if description is not None else ""

        super().__init__(
            f"{command} failed with ACK status 0x{status:02X}{suffix}"
        )
