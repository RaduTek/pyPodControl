from typing import Final

from .lingo import Lingo


class DigitalAudio(Lingo):
    """
    ### Digital Audio Lingo (0x0A)

    Digital audio output from the iPod (sample rates, track audio attributes, video delay)
    """

    LINGO_ID: Final = 0x0A

    COMMANDS = {
        "AccessoryAck": 0x00,
        "iPodAck": 0x01,
        "GetAccessorySampleRateCaps": 0x02,
        "RetAccessorySampleRateCaps": 0x03,
        "TrackNewAudioAttributes": 0x04,
        "SetVideoDelay": 0x05,
    }
    """Available commands"""

    ACK_COMMAND = "iPodAck"
