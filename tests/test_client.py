import threading

import pytest

from fake_transport import FakeTransport
from pypodcontrol import iAPAckError, iAPClient, iAPError, iAPTimeoutError
from pypodcontrol.auth import AuthenticationProvider
from pypodcontrol.lingo import ExtendedInterface, General, Lingo, SimpleRemote


class DummyAuth(AuthenticationProvider):
    @property
    def protocol_version(self):
        return (2, 0)

    def get_certificate(self):
        return b""

    def sign_challenge(self, challenge):
        return b""


@pytest.fixture
def transport():
    return FakeTransport()


@pytest.fixture
def client(transport):
    with iAPClient(transport, timeout=0.5) as iap:
        yield iap


def reply_with(transport, *payloads):
    """Inject the given payloads after the next packet is sent"""

    def on_send(_):
        transport.on_send = None
        for payload in payloads:
            transport.inject(payload)

    transport.on_send = on_send


def test_general_is_preregistered(client):
    assert isinstance(client.general, General)
    assert General in client
    assert client.get(0x00) is client.general

    with pytest.raises(ValueError):
        client.unregister(General)


def test_register_instance_and_class(client):
    sr = client.register(SimpleRemote())
    assert client.get(SimpleRemote) is sr
    assert sr.iap is client

    ei = client.register(ExtendedInterface)
    assert isinstance(ei, ExtendedInterface)

    with pytest.raises(iAPError):
        client.register(SimpleRemote())

    client.unregister(sr)
    assert SimpleRemote not in client
    with pytest.raises(iAPError):
        sr.iap


def test_lingo_bound_to_one_client(transport):
    sr = iAPClient(transport).register(SimpleRemote)
    with pytest.raises(iAPError):
        iAPClient(FakeTransport()).register(sr)


def test_command_maps():
    assert SimpleRemote.command_id("ContextButtonStatus") == 0x00
    assert SimpleRemote.command_name(0x01) == "ACK"
    assert ExtendedInterface.command_name(0x0013) == "ReturnProtocolVersion"
    assert General.command_name(0xEE) == "Unknown(0xEE)"


def test_duplicate_command_ids_rejected():
    with pytest.raises(ValueError):

        class Broken(Lingo):
            LINGO_ID = 0x7F
            COMMANDS = {"A": 0x01, "B": 0x01}


def test_identify_packet(client, transport):
    client.general.identify(SimpleRemote)
    assert transport.next_sent() == bytes.fromhex("00 01 02")


def test_extended_command_ids(client, transport):
    ei = client.register(ExtendedInterface)
    ei.send("RequestProtocolVersion")
    assert transport.next_sent() == bytes.fromhex("04 00 12")


def test_button_state_not_shared():
    a, b = SimpleRemote(), SimpleRemote()
    a.current_buttons.add("play")
    assert b.current_buttons == set()


def test_request_resolves_with_response(client, transport):
    reply_with(transport, b"\x00\x08iPod\x00")
    assert client.general.request_ipod_name() == "iPod"
    assert transport.next_sent() == bytes.fromhex("00 07")


def test_request_lingo_protocol_version(client, transport):
    reply_with(transport, bytes.fromhex("00 10 02 01 02"))
    assert client.general.request_lingo_protocol_version(SimpleRemote) == (1, 2)


def test_request_ack_error(client, transport):
    reply_with(transport, bytes.fromhex("00 02 04 0F"))

    with pytest.raises(iAPAckError) as e:
        client.general.request_lingo_protocol_version(0x7F)

    assert e.value.status == 0x04


def test_request_waits_for_ack(client, transport):
    sr = client.register(SimpleRemote)
    reply_with(transport, bytes.fromhex("02 01 00 00"))
    ack = sr.request("ContextButtonStatus", b"\x01")
    assert ack.data == b"\x00\x00"


def test_extended_ack_two_byte_command(client, transport):
    ei = client.register(ExtendedInterface)
    reply_with(transport, bytes.fromhex("04 00 01 02 00 29"))

    with pytest.raises(iAPAckError) as e:
        ei.request("PlayControl", b"\x01")

    assert e.value.status == 0x02


def test_request_timeout(client):
    with pytest.raises(iAPTimeoutError):
        client.general.request_ipod_name()


def test_command_pending_extends_deadline(client, transport):
    client.timeout = 0.1
    pending = bytes.fromhex("00 02 06 07 00 00 01 F4")  # 500 ms

    def on_send(_):
        transport.on_send = None
        transport.inject(pending)
        threading.Timer(0.3, transport.inject, [b"\x00\x08Late\x00"]).start()

    transport.on_send = on_send
    assert client.general.request_ipod_name() == "Late"


def test_unsolicited_packets_reach_listeners(client, transport):
    ei = client.register(ExtendedInterface)
    received = []
    done = threading.Event()

    def listener(packet):
        received.append(packet)
        done.set()

    ei.add_listener("PlayStatusChangeNotification", listener)
    transport.inject(bytes.fromhex("04 00 27 01 00 00 00 05"))

    assert done.wait(1)
    assert received[0].command_id == 0x0027
    assert received[0].data == bytes.fromhex("01 00 00 00 05")


def test_idps_requires_auth(transport):
    with pytest.raises(ValueError):
        iAPClient(transport, use_idps=True)


def test_idps_transaction_ids(transport):
    with iAPClient(transport, auth=DummyAuth(), use_idps=True) as iap:
        assert iap.use_idps
        assert iap.transaction_ids_enabled

        iap.general.send("RequestiPodName")
        iap.general.send("RequestiPodName")

        assert transport.next_sent() == bytes.fromhex("00 07 00 00")
        assert transport.next_sent() == bytes.fromhex("00 07 00 01")


def test_idps_response_matched_by_transaction_id(transport):
    with iAPClient(transport, auth=DummyAuth(), use_idps=True, timeout=0.5) as iap:
        # Response for another transaction is ignored, the matching one resolves
        reply_with(
            transport,
            b"\x00\x08\x00\x05Other\x00",
            b"\x00\x08\x00\x00iPod\x00",
        )
        assert iap.general.request_ipod_name() == "iPod"


def test_legacy_ack_disables_transaction_ids(transport):
    with iAPClient(transport, auth=DummyAuth(), use_idps=True, timeout=0.5) as iap:
        reply_with(transport, bytes.fromhex("00 02 04 38"))

        with pytest.raises(iAPAckError):
            iap.general.request(0x38)

        assert not iap.transaction_ids_enabled


def test_no_transaction_ids_without_idps(client, transport):
    assert not client.transaction_ids_enabled
    client.general.send("RequestiPodName")
    assert transport.next_sent() == bytes.fromhex("00 07")


def test_close_fails_pending(transport):
    iap = iAPClient(transport, timeout=5)
    iap.open()
    errors = []

    def worker():
        try:
            iap.general.request_ipod_name()
        except iAPError as e:
            errors.append(e)

    t = threading.Thread(target=worker)
    t.start()
    transport.next_sent()
    iap.close()
    t.join(1)

    assert errors and not isinstance(errors[0], iAPTimeoutError)
