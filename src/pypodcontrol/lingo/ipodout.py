from typing import Final

from .lingo import Lingo


class iPodOut(Lingo):
    """
    ### iPod Out Lingo (0x0D)

    Display of the iPod's user interface on the accessory's screen (iPod Out mode)
    """

    LINGO_ID: Final = 0x0D

    COMMANDS = {
        "iPodAck": 0x00,
        "GetiPodOutOptions": 0x01,
        "RetiPodOutOptions": 0x02,
        "SetiPodOutOptions": 0x03,
        "AccessoryStateChangeEvent": 0x04,
        "DevVideoScreenInfo": 0x06,
    }
    """Available commands"""

    ACK_COMMAND = "iPodAck"
