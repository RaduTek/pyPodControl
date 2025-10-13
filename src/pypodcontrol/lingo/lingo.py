from .. import iAPBase


class Lingo:
    """
    ### Lingo

    Base class for an iAP Lingo

    Extend this class to implement different iAP Lingos
    """

    iap: iAPBase
    lingo_id: int

    def __init__(self, iap: iAPBase, lingo_id: int) -> None:
        """Create a new instace of Lingo"""

        self.iap = iap
        self.lingo_id = lingo_id

    def send_command(self, command_id: int, command_data: bytes) -> None:
        """Send a command"""

        self.iap.send_command(self.lingo_id, command_id, command_data)
