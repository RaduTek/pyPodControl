from typing import Final

from .lingo import Lingo


class RFTuner(Lingo):
    """
    ### RF Tuner Lingo (0x07)

    Control of an accessory radio tuner by the iPod (FM, RDS and HD Radio)
    """

    LINGO_ID: Final = 0x07

    COMMANDS = {
        "AccessoryAck": 0x00,
        "GetTunerCaps": 0x01,
        "RetTunerCaps": 0x02,
        "GetTunerCtrl": 0x03,
        "RetTunerCtrl": 0x04,
        "SetTunerCtrl": 0x05,
        "GetTunerBand": 0x06,
        "RetTunerBand": 0x07,
        "SetTunerBand": 0x08,
        "GetTunerFreq": 0x09,
        "RetTunerFreq": 0x0A,
        "SetTunerFreq": 0x0B,
        "GetTunerMode": 0x0C,
        "RetTunerMode": 0x0D,
        "SetTunerMode": 0x0E,
        "GetTunerSeekRssi": 0x0F,
        "RetTunerSeekRssi": 0x10,
        "SetTunerSeekRssi": 0x11,
        "TunerSeekStart": 0x12,
        "TunerSeekDone": 0x13,
        "GetTunerStatus": 0x14,
        "RetTunerStatus": 0x15,
        "GetStatusNotifyMask": 0x16,
        "RetStatusNotifyMask": 0x17,
        "SetStatusNotifyMask": 0x18,
        "StatusChangeNotify": 0x19,
        "GetRdsReadyStatus": 0x1A,
        "RetRdsReadyStatus": 0x1B,
        "GetRdsData": 0x1C,
        "RetRdsData": 0x1D,
        "GetRdsNotifyMask": 0x1E,
        "RetRdsNotifyMask": 0x1F,
        "SetRdsNotifyMask": 0x20,
        "RdsReadyNotify": 0x21,
        "GetHDProgramServiceCount": 0x25,
        "RetHDProgramServiceCount": 0x26,
        "GetHDProgramService": 0x27,
        "RetHDProgramService": 0x28,
        "SetHDProgramService": 0x29,
        "GetHDDataReadyStatus": 0x2A,
        "RetHDDataReadyStatus": 0x2B,
        "GetHDData": 0x2C,
        "RetHDData": 0x2D,
        "GetHDDataNotifyMask": 0x2E,
        "RetHDDataNotifyMask": 0x2F,
        "SetHDDataNotifyMask": 0x30,
        "HDDataReadyNotify": 0x31,
    }
    """Available commands"""
