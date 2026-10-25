import logging
import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Final, Iterable

from ..errors import iAPAckError, iAPIdentificationError
from ..packet import Packet, encode_byte, encode_int, encode_long, encode_short
from .lingo import Lingo

logger = logging.getLogger(__name__)


class PowerOption(IntEnum):
    """Power the accessory draws from the iPod, declared during identification"""

    LOW_POWER = 0b00
    """Not more than 5 mA at any time"""

    INTERMITTENT_HIGH_POWER = 0b01
    """More than 5 mA (up to 100 mA) during playback"""

    CONSTANT_HIGH_POWER = 0b11
    """More than 5 mA (up to 100 mA) at all times, only if the accessory supplies power to the iPod"""


class FIDTokenStatus(IntEnum):
    """AckFIDTokenValues acknowledgment status"""

    ACCEPTED = 0
    REQUIRED_FAILED = 1
    OPTIONAL_FAILED = 2
    NOT_SUPPORTED = 3
    LINGOES_BUSY = 4
    MAXIMUM_CONNECTIONS = 5


@dataclass(frozen=True)
class AccessoryInfo:
    """
    ### AccessoryInfo

    Accessory information sent to the iPod during IDPS (AccessoryInfoToken)
    """

    name: str = "pyPodControl"
    manufacturer: str = "pyPodControl"
    model_number: str = "pyPodControl"
    serial_number: str | None = None
    firmware_version: tuple[int, int, int] = (1, 0, 0)
    hardware_version: tuple[int, int, int] = (1, 0, 0)
    rf_certifications: int = 0
    """RF certification declaration mask, must be 0 unless tested by an authorized lab"""

    capabilities: int = 0
    """AccessoryCapsToken capabilities bitmask (e.g. bit 0: analog line-out)"""


@dataclass(frozen=True)
class FIDTokenAck:
    """Acknowledgment of one FID token-value field"""

    fid_type: int
    fid_subtype: int
    status: int
    data: bytes = b""
    """Extra acknowledgment data, e.g. the info type of an AccessoryInfoToken"""


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
        "GetUIMode": 0x35,
        "RetUIMode": 0x36,
        "SetUIMode": 0x37,
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
        "SetAccessoryStatusNotification": 0x46,
        "RetAccessoryStatusNotification": 0x47,
        "AccessoryStatusNotification": 0x48,
        "SetEventNotification": 0x49,
        "iPodNotification": 0x4A,
        "GetiPodOptionsForLingo": 0x4B,
        "RetiPodOptionsForLingo": 0x4C,
        "GetEventNotification": 0x4D,
        "RetEventNotification": 0x4E,
        "GetSupportedEventNotification": 0x4F,
        "CancelCommand": 0x50,
        "RetSupportedEventNotification": 0x51,
        "SetAvailableCurrent": 0x54,
        "SetInternalBatteryChargingState": 0x56,
        "RequestApplicationLaunch": 0x64,
        "GetNowPlayingApplicationBundleName": 0x65,
        "RetNowPlayingApplicationBundleName": 0x66,
        "GetLocalizationInfo": 0x67,
        "RetLocalizationInfo": 0x68,
        "RequestWiFiConnectionInfo": 0x69,
        "WiFiConnectionInfo": 0x6A,
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

    AUTHENTICATE_IMMEDIATELY: Final = 0b10
    """Identification option: authenticate immediately after identification (Authentication 2.0)"""

    DEFAULT_MAX_PAYLOAD_SIZE: Final = 506
    """Max payload size of iPods that don't support RequestTransportMaxPayloadSize"""

    FID_IDENTIFY: Final = 0x00
    FID_ACCESSORY_CAPS: Final = 0x01
    FID_ACCESSORY_INFO: Final = 0x02
    """FID token subtypes (FIDType 0x00)"""

    FID_REQUIRED: Final = (FID_IDENTIFY, FID_ACCESSORY_CAPS, FID_ACCESSORY_INFO)
    """FID tokens required by IDPS"""

    ACCESSORY_INFO_NAME: Final = 0x01
    ACCESSORY_INFO_FIRMWARE_VERSION: Final = 0x04
    ACCESSORY_INFO_HARDWARE_VERSION: Final = 0x05
    ACCESSORY_INFO_MANUFACTURER: Final = 0x06
    ACCESSORY_INFO_MODEL_NUMBER: Final = 0x07
    ACCESSORY_INFO_SERIAL_NUMBER: Final = 0x08
    ACCESSORY_INFO_RF_CERTIFICATIONS: Final = 0x0C
    """AccessoryInfoToken info types"""

    MAX_CERT_SECTION: Final = 500
    """Maximum certificate bytes per RetDevAuthenticationInfo section"""

    AUTH_SUCCESS: Final = 0x00
    """AckDevAuthenticationStatus status: authenticated"""

    def __init__(self) -> None:
        super().__init__()

        self._auth_lock = threading.Lock()
        self._auth_event = threading.Event()
        self._auth_status: int | None = None
        self._cert_ack = threading.Event()
        self._cert_ack_status = 0x00

        self._info_requested: set[int | tuple[int, int]] = set()
        self._info_done = threading.Event()

    def handle_packet(self, packet: Packet) -> None:
        command_id = packet.command_id
        handled = True

        if command_id == self.command_id("RequestIdentify"):
            self._on_request_identify()
        elif command_id == self.command_id("GetDevAuthenticationInfo"):
            self._on_get_dev_authentication_info(packet.transaction_id)
        elif command_id == self.command_id("GetDevAuthenticationSignature"):
            self._on_get_dev_authentication_signature(packet)
        elif command_id == self.command_id("AckDevAuthenticationInfo"):
            self._on_cert_ack(packet.data[0] if packet.data else 0x00)
        elif command_id == self.command_id("AckDevAuthenticationStatus"):
            self._on_authentication_status(packet.data)
        elif command_id == self.command_id("GetAccessoryInfo"):
            self._on_get_accessory_info(packet)
        else:
            # An iPodAck of a certificate section releases the next section
            ack = self.parse_ack(packet)
            handled = ack is not None and ack[1] == self.command_id(
                "RetDevAuthenticationInfo"
            )
            if handled:
                self._on_cert_ack(ack[0])

        if handled:
            self.notify_listeners(packet)
        else:
            super().handle_packet(packet)

    def _on_request_identify(self) -> None:
        """The iPod asks the accessory to identify again"""

        if not self.iap.is_identified:
            return

        logger.info("iPod requested identification, identifying again")

        # Runs on the reader thread, which must stay free to receive the responses
        threading.Thread(
            target=self.iap.reidentify, name="iAP-reidentify", daemon=True
        ).start()

    # --- device authentication ------------------------------------------------
    #
    # The iPod drives authentication: it asks for the accessory's certificate
    # (GetDevAuthenticationInfo) and a signed challenge (GetDevAuthenticationSignature),
    # verifies them and reports the result (AckDevAuthenticationStatus). The
    # AuthenticationProvider supplies the certificate and signature.

    def reset_authentication(self) -> None:
        """Clear the authentication result before a new identification"""

        with self._auth_lock:
            self._auth_status = None
            self._auth_event.clear()
            self._info_requested.clear()
            self._info_done.clear()

    @property
    def authentication_status(self) -> int | None:
        """Last AckDevAuthenticationStatus status, None if not authenticated yet"""

        return self._auth_status

    def wait_for_authentication(self, timeout: float | None = None) -> bool:
        """
        Wait for authentication to finish, returns whether it passed

        After a non-IDPS identification the iPod keeps requesting accessory
        information once authentication passes, so this also waits until every
        advertised info type has been requested and answered.
        """

        deadline = None if timeout is None else time.monotonic() + timeout

        if not self._auth_event.wait(timeout):
            return False

        if self._auth_status != self.AUTH_SUCCESS:
            return False

        # IDPS sends the accessory info in FID tokens, the iPod doesn't ask for it
        if self._info_requested:
            logger.debug("Waiting for the iPod to request the remaining accessory info")
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            if not self._info_done.wait(remaining):
                logger.warning(
                    "iPod didn't request all accessory info, missing: %s",
                    self._missing_info(),
                )

        return True

    def _on_get_dev_authentication_info(self, transaction_id: int | None) -> None:
        """The iPod requests the accessory certificate"""

        if self.iap.auth is None:
            logger.warning("iPod requested authentication but no provider is set")
            return

        logger.info("iPod requested the authentication certificate")

        # Sending the certificate waits for ACKs between sections, so it must
        # not run on the reader thread that delivers those ACKs
        threading.Thread(
            target=self._send_dev_authentication_info,
            args=(transaction_id,),
            name="iAP-auth-cert",
            daemon=True,
        ).start()

    def _send_dev_authentication_info(self, transaction_id: int | None) -> None:
        auth = self.iap.auth
        if auth is None:
            return

        certificate = auth.get_certificate()
        major, minor = auth.protocol_version

        # A section must fit both the 500 byte cert limit and the transport's
        # packet payload (lingo, command, transaction ID and the 4 byte header)
        overhead = 2 + (2 if self.iap.transaction_ids_enabled else 0) + 4
        section_size = min(self.MAX_CERT_SECTION, self.iap.transport.max_payload_size - overhead)

        sections = [
            certificate[i : i + section_size]
            for i in range(0, len(certificate), section_size)
        ] or [b""]
        last = len(sections) - 1

        logger.info(
            "Sending authentication certificate: %d bytes in %d section(s)",
            len(certificate),
            len(sections),
        )

        echo = transaction_id if transaction_id is not None else False

        for index, section in enumerate(sections):
            header = bytes([major, minor, index, last])

            self._cert_ack.clear()
            self.send(
                "RetDevAuthenticationInfo", header + section, transaction_id=echo
            )

            # Every section but the last is acknowledged before the next is sent
            if index == last:
                break

            if not self._cert_ack.wait(self.iap.timeout):
                logger.warning("No acknowledgment for certificate section %d", index)
                return
            if self._cert_ack_status != 0x00:
                logger.warning(
                    "Certificate section %d rejected: status 0x%02X",
                    index,
                    self._cert_ack_status,
                )
                return

    def _on_cert_ack(self, status: int) -> None:
        if status == 0x00:
            logger.debug("Certificate acknowledged")
        else:
            logger.warning("Certificate rejected: status 0x%02X", status)

        self._cert_ack_status = status
        self._cert_ack.set()

    def _on_get_dev_authentication_signature(self, packet: Packet) -> None:
        """The iPod sends a challenge for the accessory to sign"""

        auth = self.iap.auth
        if auth is None:
            logger.warning("iPod requested a signature but no provider is set")
            return

        # The payload is the challenge followed by a 1 byte retry counter
        challenge = packet.data[:-1] if packet.data else b""
        logger.info(
            "Signing %d byte authentication challenge (retry counter %d)",
            len(challenge),
            packet.data[-1] if packet.data else 0,
        )
        signature = auth.sign_challenge(challenge)

        echo = packet.transaction_id if packet.transaction_id is not None else False
        self.send("RetDevAuthenticationSignature", signature, transaction_id=echo)

    def _on_authentication_status(self, data: bytes) -> None:
        status = data[0] if data else 0xFF

        with self._auth_lock:
            self._auth_status = status
            self._auth_event.set()

        if status == self.AUTH_SUCCESS:
            logger.info("Authentication passed")
        else:
            logger.warning("Authentication failed: status 0x%02X", status)

    # --- accessory information ------------------------------------------------
    #
    # After a non-IDPS IdentifyDeviceLingoes, the iPod asks for accessory
    # information by type (GetAccessoryInfo). The accessory must answer each
    # request, or identification/authentication stalls.

    def _on_get_accessory_info(self, packet: Packet) -> None:
        """The iPod requests a piece of accessory information"""

        info_type = packet.data[0] if packet.data else 0x00
        response = self._accessory_info(info_type, packet.data[1:])

        if response is None:
            logger.debug("No response for accessory info type 0x%02X", info_type)
        else:
            echo = packet.transaction_id if packet.transaction_id is not None else False
            self.send(
                "RetAccessoryInfo", bytes([info_type]) + response, transaction_id=echo
            )

        # Type 0x03 is requested once per lingo
        key = (info_type, packet.data[1]) if info_type == 0x03 and len(packet.data) > 1 else info_type

        with self._auth_lock:
            self._info_requested.add(key)
            if not self._missing_info() and not self._info_done.is_set():
                logger.debug("iPod requested all accessory info")
                self._info_done.set()

    def _supported_info_types(self) -> set[int]:
        """Accessory info types advertised in the capabilities response"""

        supported = {0x00, 0x01, 0x03, 0x04, 0x05, 0x06, 0x07, 0x09}
        if self.iap.accessory_info.serial_number is not None:
            supported.add(0x08)
        return supported

    def _missing_info(self) -> set[int | tuple[int, int]]:
        """Advertised accessory info the iPod hasn't requested yet"""

        expected: set[int | tuple[int, int]] = set()
        for info_type in self._supported_info_types() - {0x00}:
            if info_type == 0x03:
                expected.update((0x03, lingo_id) for lingo_id in self.iap.lingos)
            else:
                expected.add(info_type)

        return expected - self._info_requested

    def _accessory_info(self, info_type: int, params: bytes) -> bytes | None:
        """Build the RetAccessoryInfo data for a requested info type"""

        info = self.iap.accessory_info

        if info_type == 0x00:
            # Capabilities: a bit for each supported accessory info type
            mask = 0
            for supported_type in self._supported_info_types():
                mask |= 1 << supported_type
            return encode_int(mask)

        if info_type == self.ACCESSORY_INFO_NAME:
            return self._info_string(info.name)
        if info_type == 0x03:  # minimum supported version of the requested lingo
            lingo_id = params[0] if params else 0x00
            return bytes([lingo_id, 1, 0])
        if info_type == self.ACCESSORY_INFO_FIRMWARE_VERSION:
            return bytes(info.firmware_version)
        if info_type == self.ACCESSORY_INFO_HARDWARE_VERSION:
            return bytes(info.hardware_version)
        if info_type == self.ACCESSORY_INFO_MANUFACTURER:
            return self._info_string(info.manufacturer)
        if info_type == self.ACCESSORY_INFO_MODEL_NUMBER:
            return self._info_string(info.model_number)
        if info_type == self.ACCESSORY_INFO_SERIAL_NUMBER and info.serial_number:
            return self._info_string(info.serial_number)
        if info_type == 0x09:  # incoming maximum payload size (>= 128)
            return encode_short(self.DEFAULT_MAX_PAYLOAD_SIZE)
        if info_type == 0x0B:  # supported status types: none
            return encode_int(0)

        return None

    @staticmethod
    def identify_options(
        authenticate: bool, power: PowerOption = PowerOption.LOW_POWER
    ) -> int:
        """Encode the options of IdentifyDeviceLingoes / IdentifyToken"""

        options = General.AUTHENTICATE_IMMEDIATELY if authenticate else 0
        return options | (PowerOption(power) << 2)

    @staticmethod
    def lingoes_mask(lingo_ids: Iterable[int]) -> int:
        """Encode lingo IDs as the Device Lingoes Spoken bit field"""

        mask = 1 << General.LINGO_ID
        for lingo_id in lingo_ids:
            mask |= 1 << lingo_id
        return mask

    def identify_device_lingoes(
        self, lingo_ids: Iterable[int], options: int = 0, device_id: int = 0
    ) -> None:
        """
        Identify the lingoes supported by the accessory (non-IDPS identification)

        - lingo_ids: IDs of the supported lingoes (General is always included)
        - options: Identification options, see identify_options()
        - device_id: Device ID from the authentication coprocessor, 0 without authentication
        """

        # IdentifyDeviceLingoes never carries a transaction ID, and disables them
        self.iap.transaction_ids_enabled = False

        logger.debug(
            "IdentifyDeviceLingoes: lingoes 0x%08X, options 0x%08X, device ID 0x%08X",
            self.lingoes_mask(lingo_ids),
            options,
            device_id,
        )

        self.request(
            "IdentifyDeviceLingoes",
            encode_int(self.lingoes_mask(lingo_ids))
            + encode_int(options)
            + encode_int(device_id),
        )

    def start_idps(self) -> None:
        """Start the IDPS process, raises iAPAckError if the iPod refuses it"""

        # Transaction IDs are required from StartIDPS onwards
        self.iap.transaction_ids_enabled = True

        self.request("StartIDPS")

    def request_transport_max_payload_size(self) -> int:
        """Get the maximum payload size of the current transport"""

        try:
            response = self.request(
                "RequestTransportMaxPayloadSize",
                response="ReturnTransportMaxPayloadSize",
            )
        except iAPAckError as e:
            if e.status != 0x04:
                raise
            return self.DEFAULT_MAX_PAYLOAD_SIZE

        if len(response.data) < 2:
            raise ValueError(f"Malformed max payload response: {response.data.hex(' ')}")

        return int.from_bytes(response.data[:2], "big")

    @staticmethod
    def fid_token(fid_subtype: int, data: bytes = b"", fid_type: int = 0x00) -> bytes:
        """Encode a FID token-value field"""

        return encode_byte(len(data) + 2) + bytes([fid_type, fid_subtype]) + data

    @staticmethod
    def _info_string(value: str) -> bytes:
        data = value.encode("utf-8") + b"\x00"
        if len(data) > 64:
            raise ValueError(f"Accessory info string too long: {value!r}")
        return data

    @staticmethod
    def identify_token(lingo_ids: Iterable[int], options: int, device_id: int) -> bytes:
        """Encode an IdentifyToken"""

        lingoes = sorted({General.LINGO_ID, *lingo_ids})

        return General.fid_token(
            General.FID_IDENTIFY,
            encode_byte(len(lingoes))
            + bytes(lingoes)
            + encode_int(options)
            + encode_int(device_id),
        )

    @staticmethod
    def accessory_tokens(info: AccessoryInfo) -> list[bytes]:
        """Encode the AccessoryCapsToken and AccessoryInfoTokens describing the accessory"""

        def info_token(info_type: int, data: bytes) -> bytes:
            return General.fid_token(
                General.FID_ACCESSORY_INFO, encode_byte(info_type) + data
            )

        tokens = [
            General.fid_token(General.FID_ACCESSORY_CAPS, encode_long(info.capabilities)),
            info_token(General.ACCESSORY_INFO_NAME, General._info_string(info.name)),
            info_token(General.ACCESSORY_INFO_FIRMWARE_VERSION, bytes(info.firmware_version)),
            info_token(General.ACCESSORY_INFO_HARDWARE_VERSION, bytes(info.hardware_version)),
            info_token(
                General.ACCESSORY_INFO_MANUFACTURER, General._info_string(info.manufacturer)
            ),
            info_token(
                General.ACCESSORY_INFO_MODEL_NUMBER, General._info_string(info.model_number)
            ),
        ]

        if info.serial_number is not None:
            tokens.append(
                info_token(
                    General.ACCESSORY_INFO_SERIAL_NUMBER,
                    General._info_string(info.serial_number),
                )
            )

        tokens.append(
            info_token(General.ACCESSORY_INFO_RF_CERTIFICATIONS, encode_int(info.rf_certifications))
        )

        return tokens

    @staticmethod
    def parse_fid_token_acks(data: bytes) -> list[FIDTokenAck]:
        """Parse the acknowledgments of an AckFIDTokenValues response"""

        if not data:
            raise ValueError("Empty AckFIDTokenValues response")

        acks = []
        offset = 1

        for _ in range(data[0]):
            length = data[offset]
            field = data[offset + 1 : offset + 1 + length]
            if len(field) < 3:
                raise ValueError(f"Malformed AckFIDTokenValues response: {data.hex(' ')}")

            acks.append(FIDTokenAck(field[0], field[1], field[2], bytes(field[3:])))
            offset += 1 + length

        return acks

    def set_fid_token_values(self, tokens: list[bytes]) -> list[FIDTokenAck]:
        """
        Send FID token-value fields, split across as few packets as the
        transport's max payload size allows, and return their acknowledgments
        """

        # Lingo ID, command ID, transaction ID and token count
        overhead = 5
        max_size = self.iap.transport.max_payload_size - overhead

        batches: list[list[bytes]] = [[]]
        for token in tokens:
            if len(token) > max_size:
                raise ValueError(f"FID token too large for transport: {token.hex(' ')}")
            if sum(map(len, batches[-1])) + len(token) > max_size:
                batches.append([])
            batches[-1].append(token)

        acks = []
        for batch in batches:
            # The iPod must acknowledge each packet before the next is sent
            response = self.request(
                "SetFIDTokenValues",
                encode_byte(len(batch)) + b"".join(batch),
                response="RetFIDTokenValueACKs",
            )
            acks += self.parse_fid_token_acks(response.data)

        return acks

    def end_idps(self, status: int = 0) -> int:
        """
        End the IDPS process, returns the iPod's IDPS status (0: success,
        authentication proceeds)

        - status: accEndIDPSStatus, 0 to finish and continue with authentication
        """

        response = self.request(
            "EndIDPS", encode_byte(status), response="IDPSStatus"
        )

        if not response.data:
            raise ValueError("Empty IDPSStatus response")

        return response.data[0]

    def run_idps(
        self,
        lingo_ids: Iterable[int],
        options: int,
        device_id: int,
        info: AccessoryInfo,
    ) -> list[FIDTokenAck]:
        """
        Identify using the full IDPS process

        StartIDPS, RequestTransportMaxPayloadSize, SetFIDTokenValues, EndIDPS.
        Raises iAPAckError with status 0x04 if the iPod doesn't support IDPS.
        """

        self.start_idps()

        transport = self.iap.transport
        transport.max_payload_size = min(
            transport.max_payload_size, self.request_transport_max_payload_size()
        )
        logger.debug("Max payload size: %d bytes", transport.max_payload_size)

        tokens = [self.identify_token(lingo_ids, options, device_id)]
        tokens += self.accessory_tokens(info)

        acks = self.set_fid_token_values(tokens)

        for ack in acks:
            logger.debug(
                "FID token %02X:%02X status %d", ack.fid_type, ack.fid_subtype, ack.status
            )

            if ack.status == FIDTokenStatus.ACCEPTED:
                continue

            required = ack.fid_type == 0x00 and ack.fid_subtype in self.FID_REQUIRED
            if not required or ack.status in (
                FIDTokenStatus.OPTIONAL_FAILED,
                FIDTokenStatus.NOT_SUPPORTED,
            ):
                logger.warning("FID token %02X:%02X not accepted: %s", ack.fid_type, ack.fid_subtype, ack)
                continue

            # Abandon IDPS, the iPod would reject it anyway
            logger.warning("Abandoning IDPS")
            self.send("EndIDPS", encode_byte(2))

            if ack.status == FIDTokenStatus.LINGOES_BUSY:
                raise iAPIdentificationError(
                    f"Lingoes busy on another accessory: {ack.data.hex(' ')}"
                )
            if ack.status == FIDTokenStatus.MAXIMUM_CONNECTIONS:
                raise iAPIdentificationError("Maximum number of accessory connections reached")

            raise iAPIdentificationError(
                f"Required FID token {ack.fid_type:02X}:{ack.fid_subtype:02X} rejected (status {ack.status})"
            )

        idps_status = self.end_idps(0)
        logger.debug("IDPS status: %d", idps_status)
        if idps_status != 0:
            raise iAPIdentificationError(f"IDPS failed with status {idps_status}")

        return acks

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
