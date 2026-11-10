from typing import Final

from .lingo import Lingo


class Sports(Lingo):
    """
    ### Sports Lingo (0x09)

    Nike + iPod cardio equipment (user data exchange)
    """

    LINGO_ID: Final = 0x09

    COMMANDS = {
        "AccessoryAck": 0x00,
        "GetAccessoryVersion": 0x01,
        "RetAccessoryVersion": 0x02,
        "GetAccessoryCaps": 0x03,
        "RetAccessoryCaps": 0x04,
        "iPodAck": 0x80,
        "GetiPodCaps": 0x83,
        "RetiPodCaps": 0x84,
        "GetUserIndex": 0x85,
        "RetUserIndex": 0x86,
        "GetUserData": 0x88,
        "RetUserData": 0x89,
        "SetUserData": 0x8A,
    }
    """Available commands"""

    ACK_COMMAND = "iPodAck"
