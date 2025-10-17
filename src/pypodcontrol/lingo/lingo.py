from .. import iAPClient


class Lingo:
    """
    ### Lingo

    Base class for an iAP Lingo

    Extend this class to implement different iAP Lingos
    """

    iap: iAPClient
    lingo_id: int

    commands: dict = {}

    def __init__(self, iap: iAPClient) -> None:
        """Create a new instace of Lingo"""

        self.iap = iap

    def get_command_id(self, command: str) -> int:
        """Get the ID of given command"""

        return self.commands[command]

    def send_command(self, command: str, command_data: bytes = b"") -> None:
        """Send a command by name"""

        command_id = self.get_command_id(command)

        self.iap.send_command(self.lingo_id, command_id, command_data)

    def send_command_id(self, command_id: int, command_data: bytes = b"") -> None:
        """Send a command by ID"""

        self.iap.send_command(self.lingo_id, command_id, command_data)
