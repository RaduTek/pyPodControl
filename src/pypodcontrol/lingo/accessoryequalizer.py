from typing import Final

from .lingo import Lingo


class AccessoryEqualizer(Lingo):
    """
    ### Accessory Equalizer Lingo (0x08)

    Control of the accessory's equalizer settings by the iPod
    """

    LINGO_ID: Final = 0x08

    COMMANDS = {
        "AccessoryAck": 0x00,
        "GetCurrentEQIndex": 0x01,
        "RetCurrentEQIndex": 0x02,
        "SetCurrentEQIndex": 0x03,
        "GetEQSettingCount": 0x04,
        "RetEQSettingCount": 0x05,
        "GetEQIndexName": 0x06,
        "RetEQIndexName": 0x07,
    }
    """Available commands"""
