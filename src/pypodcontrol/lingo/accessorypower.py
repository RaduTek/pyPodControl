from .. import iAPClient
from . import Lingo


class AccessoryPower(Lingo):
    """
    ### Accessory Power Lingo (0x05)

    Request high power use from iPod
    """

    lingo_id = 0x05

    commands = {
        "BeginHighPower": 0x02,
        "EndHighPower": 0x03,
    }
    """Available commands"""

    def __init__(self, iap: iAPClient) -> None:
        """Create a new instance of AccessoryPower"""

        super().__init__(iap)

    def begin_high_power(self) -> None:
        """Notify iPod that accessory may use high power (> 5mA)"""

        self.send_command("BeginHighPower")
