from typing import Final

from .lingo import Lingo


class Location(Lingo):
    """
    ### Location Lingo (0x0E)

    Location data (e.g. GPS) provided by the accessory to the iPod
    """

    LINGO_ID: Final = 0x0E

    COMMANDS = {
        "AccessoryAck": 0x00,
        "GetAccessoryCaps": 0x01,
        "RetAccessoryCaps": 0x02,
        "GetAccessoryControl": 0x03,
        "RetAccessoryControl": 0x04,
        "SetAccessoryControl": 0x05,
        "GetAccessoryData": 0x06,
        "RetAccessoryData": 0x07,
        "SetAccessoryData": 0x08,
        "AsyncAccessoryData": 0x09,
        "iPodAck": 0x80,
    }
    """Available commands"""

    ACK_COMMAND = "iPodAck"
