from .. import iAPBase
from . import Lingo


class General(Lingo):
    """
    ### General Lingo (0x00)

    Implements housekeeping commands supported by all iPods
    """

    lingo_id = 0x00

    commands = {
        "RequestIdentify": 0x0,
        "Identify": 0x01,
        "ACK": 0x02,
        "RequestRemoteUIMode": 0x03,
        "ReturnRemoteUIMode": 0x04,
        "EnterRemoteUIMode": 0x05,
        "ExitRemoteUIMode": 0x06,
        "RequestiPodName": 0x07,
        "ReturniPodName": 0x08,
        "RequestiPodSoftwareVersion": 0x09,
        "ReturniPodSoftwareVersion": 0x0A,
        "RequestiPodSerialNum": 0x0B,
        "ReturniPodSerialNum": 0x0C,
        "RequestiPodModelNum": 0x0D,
        "ReturniPodModelNum": 0x0E,
        "RequestLingoProtocolVersion": 0x0F,
        "ReturnLingoProtocolVersion": 0x10,
        "IdentifyDeviceLingoes": 0x13,
        "GetDevAuthenticationInfo": 0x14,
        "RetDevAuthenticationInfo": 0x15,
        "AckDevAuthenticationInfo": 0x16,
        "GetDevAuthenticationSignature": 0x17,
        "RetDevAuthenticationSignature": 0x18,
        "AckDevAuthenticationStatus": 0x19,
        "GetiPodAuthenticationInfo": 0x1A,
        "RetiPodAuthenticationInfo": 0x1B,
        "AckiPodAuthenticationInfo": 0x1C,
        "GetiPodAuthenticationSignature": 0x1D,
        "RetiPodAuthenticationSignature": 0x1E,
        "AckiPodAuthenticationStatus": 0x1F,
        "NotifyiPodStateChange": 0x23,
        "GetiPodOptions": 0x24,
        "RetiPodOptions": 0x25,
        "GetAccessoryInfo": 0x27,
        "RetAccessoryInfo": 0x28,
        "GetiPodPreferences": 0x29,
        "RetiPodPreferences": 0x2A,
        "SetiPodPreferences": 0x2B,
        "StartIDPS": 0x38,
        "SetFIDTokenValues": 0x39,
        "RetFIDTokenValueACKs": 0x3A,
        "EndIDPS": 0x3B,
        "IDPSStatus": 0x3C,
        "OpenDataSessionForProtocol": 0x3F,
        "CloseDataSession": 0x40,
        "DevACK": 0x41,
        "DevDataTransfer": 0x42,
        "iPodDataTransfer": 0x43,
        "SetEventNotification": 0x49,
        "iPodNotification": 0x4A,
        "GetiPodOptionsForLingo": 0x4B,
        "RetiPodOptionsForLingo": 0x4C,
        "GetEventNotification": 0x4D,
        "RetEventNotification": 0x4E,
        "GetSupportedEventNotification": 0x4F,
        "RetSupportedEventNotification": 0x51,
    }
    """Available commands"""

    def __init__(self, iap: iAPBase) -> None:
        """Create a new instance of General"""

        super().__init__(iap)

    def identify(self, lingo: int | type | Lingo) -> None:
        """
        Notify the iPod that the accessory supports the given lingo

        This is deprecated, and should only be used for the 3rd gen iPod
        """

        if isinstance(lingo, int):
            lingo_id = lingo
        elif isinstance(lingo, type) and issubclass(lingo, Lingo):
            lingo_id = getattr(lingo, "lingo_id")
        elif isinstance(lingo, Lingo):
            lingo_id = getattr(lingo, "lingo_id")
        else:
            raise TypeError("lingo must be int, Lingo subclass, or Lingo instance")

        self.send_command("Identify", iAPBase.encode_byte(lingo_id))
