from typing import Final

from ..packet import encode_byte
from .lingo import Lingo


class General(Lingo):
    """
    ### General Lingo (0x00)

    Implements housekeeping commands supported by all iPods
    """

    LINGO_ID: Final = 0x00

    COMMANDS = {
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
        "RequestTransportMaxPayloadSize": 0x11,
        "ReturnTransportMaxPayloadSize": 0x12,
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

    ACK_COMMAND = "ACK"

    ACK_STATUSES = {
        0x00: "Success",
        0x01: "Unknown database category or session ID",
        0x02: "Command failed",
        0x03: "Out of resources",
        0x04: "Bad parameter",
        0x05: "Unknown ID",
        0x06: "Command pending",
        0x07: "Not authenticated",
        0x08: "Bad authentication version",
        0x09: "Accessory power mode request failed",
        0x0A: "Certificate invalid",
        0x0B: "Certificate permissions invalid",
        0x0C: "File is in use",
        0x0D: "Invalid file handle",
        0x0E: "Directory not empty",
        0x0F: "Operation timed out",
        0x10: "Command unavailable in this mode",
        0x11: "Accessory detect not grounded or invalid identify resistor",
        0x12: "Selection not Genius",
        0x13: "Multisection data section received",
        0x14: "Lingo busy",
        0x15: "Maximum number of accessory connections reached",
        0x16: "HID descriptor index already in use",
        0x17: "Dropped data",
        0x18: "Incompatible video settings for iPod Out",
    }
    """ACK status codes, shared by all lingos"""

    def identify(self, lingo: int | type | Lingo) -> None:
        """
        Notify the iPod that the accessory supports the given lingo

        This is deprecated, and should only be used for the 3rd gen iPod
        """

        if isinstance(lingo, int):
            lingo_id = lingo
        elif isinstance(lingo, type) and issubclass(lingo, Lingo):
            lingo_id = lingo.LINGO_ID
        elif isinstance(lingo, Lingo):
            lingo_id = lingo.LINGO_ID
        else:
            raise TypeError("lingo must be int, Lingo subclass, or Lingo instance")

        # Identify never carries a transaction ID, and disables them
        self.iap.transaction_ids_enabled = False
        self.send("Identify", encode_byte(lingo_id), transaction_id=False)

    def request_ipod_name(self) -> str:
        """Get the name of the iPod"""

        response = self.request("RequestiPodName", response="ReturniPodName")

        return response.data.split(b"\x00", 1)[0].decode("utf-8", errors="replace")

    def request_lingo_protocol_version(
        self, lingo: int | type[Lingo] | Lingo
    ) -> tuple[int, int]:
        """Get the iPod's protocol version (major, minor) of the given lingo"""

        lingo_id = lingo if isinstance(lingo, int) else lingo.LINGO_ID

        response = self.request(
            "RequestLingoProtocolVersion",
            encode_byte(lingo_id),
            response="ReturnLingoProtocolVersion",
        )

        if len(response.data) < 3:
            raise ValueError(f"Malformed version response: {response.data.hex(' ')}")

        return response.data[1], response.data[2]
