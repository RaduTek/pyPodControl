from typing import Final

from .lingo import Lingo


class AccessoryPower(Lingo):
    """
    ### Accessory Power Lingo (0x05)

    Request high power use from iPod
    """

    LINGO_ID: Final = 0x05

    COMMANDS = {
        "BeginHighPower": 0x02,
        "EndHighPower": 0x03,
    }
    """Available commands"""

    def begin_high_power(self) -> None:
        """Notify iPod that accessory may use high power (> 5mA)"""

        self.send("BeginHighPower")

    def end_high_power(self) -> None:
        """Notify iPod that accessory no longer uses high power"""

        self.send("EndHighPower")
