from typing import Final

from .lingo import Lingo


class USBHostMode(Lingo):
    """
    ### USB Host Mode Lingo (0x06)

    USB host mode of the iPod, and the deprecated USB Host Control power state commands
    """

    LINGO_ID: Final = 0x06

    COMMANDS = {
        "AccessoryAck": 0x00,
        "GetUSBPowerState": 0x01,
        "RetUSBPowerState": 0x02,
        "SetUSBPowerState": 0x03,
        "NotifyUSBMode": 0x04,
        "iPodAck": 0x80,
        "GetiPodUSBMode": 0x81,
        "RetiPodUSBMode": 0x82,
        "SetiPodUSBMode": 0x83,
    }
    """Available commands"""

    ACK_COMMAND = "iPodAck"
