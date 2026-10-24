import logging

from fake_transport import FakeTransport
from test_identify import FakeiPod
from pypodcontrol import TRAFFIC_LOGGER, iAPClient
from pypodcontrol.debug import describe_packet
from pypodcontrol.lingo import General, SimpleRemote
from pypodcontrol.packet import Packet


def test_describe_command():
    packet = Packet(0x00, 0x0F, b"\x02", None)
    assert describe_packet(General(), packet) == "General.RequestLingoProtocolVersion 02"


def test_describe_transaction_id_and_ack():
    packet = Packet(0x00, 0x02, b"\x04\x38", 7)
    assert describe_packet(General(), packet) == "General.ACK #7 (Bad parameter: StartIDPS) 04 38"


def test_describe_long_data():
    packet = Packet(0x00, 0x08, bytes(20), None)
    assert describe_packet(General(), packet).startswith("General.ReturniPodName [20 bytes] 00 00")


def test_describe_unregistered_lingo():
    packet = Packet(0x0A, 0x02, b"", None)
    assert describe_packet(None, packet) == "DigitalAudio.Unknown(0x02)"


def test_traffic_logged(caplog):
    transport = FakeTransport()
    FakeiPod(transport, idps=False)

    with caplog.at_level(logging.DEBUG, logger=TRAFFIC_LOGGER):
        with iAPClient(transport, timeout=0.5) as iap:
            iap.register(SimpleRemote)
            iap.start_identify(authenticate=False)

    messages = [r.getMessage() for r in caplog.records if r.name == TRAFFIC_LOGGER]
    assert messages[0].startswith("-> General.IdentifyDeviceLingoes ")
    assert messages[1] == "<- General.ACK (Success: IdentifyDeviceLingoes) 00 13"


def test_handled_command_not_logged_unhandled(caplog):
    transport = FakeTransport()

    with caplog.at_level(logging.DEBUG, logger="pypodcontrol.lingo"):
        with iAPClient(transport) as iap:
            from test_auth import _collect_accessory_info

            _collect_accessory_info(iap, transport, 0x01)

    assert "unhandled" not in caplog.text
