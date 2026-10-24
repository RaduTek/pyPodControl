import threading

import pytest

from fake_transport import FakeTransport
from test_client import DummyAuth
from pypodcontrol import (
    AccessoryInfo,
    PowerOption,
    iAPAckError,
    iAPClient,
    iAPIdentificationError,
)
from pypodcontrol.lingo import ExtendedInterface, General, SimpleRemote
from pypodcontrol.packet import Packet


def test_identify_options():
    assert General.identify_options(False) == 0b0000
    assert General.identify_options(True) == 0b0010
    assert General.identify_options(False, PowerOption.INTERMITTENT_HIGH_POWER) == 0b0100
    assert General.identify_options(True, PowerOption.CONSTANT_HIGH_POWER) == 0b1110


def test_lingoes_mask():
    # Example from the spec: Simple Remote + RF Tuner
    assert General.lingoes_mask([0x02, 0x07]) == 0x85


def test_identify_device_lingoes(transport_with_ack):
    transport, iap = transport_with_ack
    iap.register(SimpleRemote)
    iap.register(ExtendedInterface)

    iap.start_identify(power_options=PowerOption.INTERMITTENT_HIGH_POWER)

    assert transport.next_sent() == bytes.fromhex(
        "00 13" "00 00 00 15" "00 00 00 04" "00 00 00 00"
    )
    assert iap.is_identified


def test_identify_device_lingoes_with_auth():
    transport = FakeTransport()
    ipod = FakeiPod(transport, idps=False)
    with iAPClient(transport, auth=DummyAuth(), timeout=0.5) as iap:
        iap.start_identify()

    assert ipod.received[0] == bytes.fromhex(
        "00 13" "00 00 00 01" "00 00 00 02" "00 00 02 00"
    )


def test_authenticate_requires_provider(transport_with_ack):
    _, iap = transport_with_ack
    with pytest.raises(ValueError):
        iap.start_identify(authenticate=True)


def test_identify_rejected():
    transport = FakeTransport()
    FakeiPod(transport, idps=False, identify_status=0x02)

    with iAPClient(transport, timeout=0.5) as iap:
        with pytest.raises(iAPAckError) as e:
            iap.start_identify()

    assert e.value.status == 0x02


class FakeiPod:
    """Responds to identification commands like an iPod would"""

    def __init__(
        self,
        transport: FakeTransport,
        idps: bool = True,
        identify_status: int = 0x00,
        max_payload: int | None = 500,
        token_status: dict[int, int] | None = None,
        drive_auth: bool = True,
        auth_status: int = 0x00,
    ) -> None:
        self.transport = transport
        self.idps = idps
        self.identify_status = identify_status
        self.max_payload = max_payload
        self.token_status = token_status or {}
        self.drive_auth = drive_auth
        self.auth_status = auth_status
        self.received: list[bytes] = []
        self.tokens: list[bytes] = []
        self.certificate = bytearray()
        self.signature: bytes | None = None
        self.tid_enabled = False
        transport.on_send = self.on_send

    @property
    def auth_tid(self) -> int | None:
        # During auth the iPod reuses a single transaction ID
        return 0x00 if self.tid_enabled else None

    def reply(self, command: int, data: bytes, transaction_id: int | None) -> None:
        self.transport.inject(Packet(0x00, command, data, transaction_id).to_payload())

    def ack(self, status: int, command: int, transaction_id: int | None) -> None:
        self.reply(0x02, bytes([status, command]), transaction_id)

    def start_authentication(self) -> None:
        if self.drive_auth:
            self.reply(0x14, b"", self.auth_tid)  # GetDevAuthenticationInfo

    def on_send(self, payload: bytes) -> None:
        self.received.append(payload)
        command = payload[1]

        if command == 0x13:
            self.ack(self.identify_status, command, None)
            if self.identify_status == 0x00:
                options = int.from_bytes(payload[6:10], "big")
                if options & 0b10:  # authenticate immediately
                    self.start_authentication()
            return

        if command == 0x38 and not self.idps:
            # Old iPod: bad parameter, without transaction ID
            self.ack(0x04, command, None)
            return

        if command == 0x38:
            # StartIDPS and every command after it carries a transaction ID
            self.tid_enabled = True

        packet = Packet.from_payload(payload, has_transaction_id=self.tid_enabled)
        tid = packet.transaction_id

        if command == 0x38:
            self.ack(0x00, command, tid)
        elif command == 0x11:
            if self.max_payload is None:
                self.ack(0x04, command, tid)
            else:
                self.reply(0x12, self.max_payload.to_bytes(2, "big"), tid)
        elif command == 0x39:
            count, data = packet.data[0], packet.data[1:]
            acks = b""
            for _ in range(count):
                token = data[: data[0] + 1]
                data = data[data[0] + 1 :]
                self.tokens.append(token)
                subtype = token[2]
                status = self.token_status.get(subtype, 0)
                extra = token[3:4] if subtype == 0x02 else b""
                acks += bytes([3 + len(extra), 0x00, subtype, status]) + extra
            self.reply(0x3A, bytes([count]) + acks, tid)
        elif command == 0x3B:
            if packet.data[0] == 0:
                self.reply(0x3C, b"\x00", tid)
                self.start_authentication()
        elif command == 0x15:  # RetDevAuthenticationInfo
            index, maximum = packet.data[2], packet.data[3]
            self.certificate += packet.data[4:]
            if index < maximum:
                self.ack(0x00, command, tid)  # acknowledge intermediate section
            else:
                self.reply(0x16, b"\x00", tid)  # AckDevAuthenticationInfo
                # GetDevAuthenticationSignature: 20 byte challenge + retry counter
                self.reply(0x17, bytes(range(20)) + b"\x01", self.auth_tid)
        elif command == 0x18:  # RetDevAuthenticationSignature
            self.signature = packet.data
            self.reply(0x19, bytes([self.auth_status]), self.auth_tid)


@pytest.fixture
def transport_with_ack():
    transport = FakeTransport()
    FakeiPod(transport, idps=False)
    with iAPClient(transport, timeout=0.5) as iap:
        yield transport, iap


def idps_client(transport, **kwargs):
    return iAPClient(transport, auth=DummyAuth(), use_idps=True, timeout=0.5, **kwargs)


def test_idps_requires_authentication():
    with idps_client(FakeTransport()) as iap:
        with pytest.raises(ValueError):
            iap.start_identify(authenticate=False)


def test_idps_flow():
    transport = FakeTransport()
    ipod = FakeiPod(transport)
    info = AccessoryInfo(name="Remote", serial_number="123")

    with idps_client(transport, accessory_info=info) as iap:
        iap.register(SimpleRemote)
        iap.start_identify(power_options=PowerOption.INTERMITTENT_HIGH_POWER)

        assert iap.is_identified
        assert iap.transaction_ids_enabled
        assert transport.max_payload_size == 500

    commands = [p[1] for p in ipod.received]
    # IDPS, then the device authentication handshake
    assert commands == [0x38, 0x11, 0x39, 0x3B, 0x15, 0x18]

    # The identification commands count transaction IDs up from 0
    assert [int.from_bytes(p[2:4], "big") for p in ipod.received[:4]] == [0, 1, 2, 3]
    assert ipod.signature is not None

    # IdentifyToken first: lingoes 0x00 + 0x02, options, device ID
    assert ipod.tokens[0] == bytes.fromhex("0D 00 00 02 00 02 00 00 00 06 00 00 02 00")
    assert ipod.tokens[1] == bytes.fromhex("0A 00 01 00 00 00 00 00 00 00 00")
    assert ipod.tokens[2] == bytes.fromhex("0A 00 02 01") + b"Remote\x00"

    info_types = [t[3] for t in ipod.tokens if t[2] == 0x02]
    assert info_types == [0x01, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0C]

    # EndIDPS (the 4th command) carries accEndIDPSStatus 0 (finish, authenticate)
    assert ipod.received[3][1] == 0x3B and ipod.received[3][4:] == b"\x00"


def test_idps_tokens_split_by_max_payload():
    transport = FakeTransport()
    ipod = FakeiPod(transport, max_payload=40)

    with idps_client(transport) as iap:
        iap.start_identify()

    set_tokens = [p for p in ipod.received if p[1] == 0x39]
    assert len(set_tokens) > 1
    assert all(len(p) <= 40 for p in set_tokens)
    assert ipod.tokens[0][2] == 0x00
    assert len(ipod.tokens) == 8


def test_idps_default_max_payload():
    transport = FakeTransport()
    FakeiPod(transport, max_payload=None)

    with idps_client(transport) as iap:
        iap.start_identify()
        assert transport.max_payload_size == 506


def test_idps_falls_back_to_identify_device_lingoes():
    transport = FakeTransport()
    ipod = FakeiPod(transport, idps=False)

    with idps_client(transport) as iap:
        iap.register(SimpleRemote)
        iap.start_identify()

        assert iap.is_identified
        assert not iap.transaction_ids_enabled

    assert [p[1] for p in ipod.received] == [0x38, 0x13, 0x15, 0x18]
    assert ipod.received[1] == bytes.fromhex(
        "00 13" "00 00 00 05" "00 00 00 02" "00 00 02 00"
    )


def test_idps_required_token_rejected():
    transport = FakeTransport()
    ipod = FakeiPod(transport, token_status={0x01: 1})

    with idps_client(transport) as iap:
        with pytest.raises(iAPIdentificationError):
            iap.start_identify()

        assert not iap.is_identified

    # Abandons IDPS
    assert ipod.received[-1][1] == 0x3B and ipod.received[-1][4] == 0x02


def test_idps_optional_failure_is_tolerated():
    transport = FakeTransport()
    FakeiPod(transport, token_status={0x02: 2})

    with idps_client(transport) as iap:
        iap.start_identify()
        assert iap.is_identified


def test_request_identify_triggers_reidentify():
    transport = FakeTransport()
    ipod = FakeiPod(transport, idps=False)

    with iAPClient(transport, timeout=0.5) as iap:
        iap.start_identify()

        done = threading.Event()
        original = ipod.on_send

        def on_send(payload):
            original(payload)
            if payload[1] == 0x13:
                done.set()

        transport.on_send = on_send
        transport.inject(b"\x00\x00")

        assert done.wait(1)

    assert [p[1] for p in ipod.received] == [0x13, 0x13]
