from typing import Final

from .lingo import Lingo


class Microphone(Lingo):
    """
    ### Microphone Lingo (0x01)

    Deprecated: audio recording accessories (voice recorders)
    """

    LINGO_ID: Final = 0x01

    COMMANDS = {
        "BeginRecord": 0x00,
        "EndRecord": 0x01,
        "BeginPlayback": 0x02,
        "EndPlayback": 0x03,
        "AccessoryAck": 0x04,
        "GetAccessoryAck": 0x05,
        "iPodModeChange": 0x06,
        "GetAccessoryCaps": 0x07,
        "RetAccessoryCaps": 0x08,
        "GetAccessoryCtrl": 0x09,
        "RetAccessoryCtrl": 0x0A,
        "SetAccessoryCtrl": 0x0B,
    }
    """Available commands"""
