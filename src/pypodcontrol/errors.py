class iAPError(Exception):
    """Base class for all pyPodControl errors"""


class TransportError(iAPError):
    """Transport failed to open, read or write"""


class iAPTimeoutError(iAPError, TimeoutError):
    """No response was received from the iPod within the timeout period"""


class iAPAckError(iAPError):
    """iPod acknowledged a command with a non-success status"""

    status: int
    """ACK status code returned by the iPod"""

    command: str
    """Name of the acknowledged command"""

    def __init__(self, status: int, command: str) -> None:
        self.status = status
        self.command = command

        super().__init__(f"{command} failed with ACK status 0x{status:02X}")
