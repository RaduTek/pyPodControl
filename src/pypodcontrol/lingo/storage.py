from typing import Final

from .lingo import Lingo


class Storage(Lingo):
    """
    ### Storage Lingo (0x0C)

    Writing files to the iPod's storage (e.g. iTunes Tagging and Nike + iPod data)
    """

    LINGO_ID: Final = 0x0C

    COMMANDS = {
        "iPodAck": 0x00,
        "GetiPodCaps": 0x01,
        "RetiPodCaps": 0x02,
        "RetiPodFileHandle": 0x04,
        "WriteiPodFileData": 0x07,
        "CloseiPodFile": 0x08,
        "GetiPodFreeSpace": 0x10,
        "RetiPodFreeSpace": 0x11,
        "OpeniPodFeatureFile": 0x12,
        "AccessoryAck": 0x80,
        "GetAccessoryCaps": 0x81,
        "RetAccessoryCaps": 0x82,
    }
    """Available commands"""

    ACK_COMMAND = "iPodAck"
