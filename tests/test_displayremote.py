import threading
from datetime import datetime

import pytest

from fake_transport import FakeTransport
from pypodcontrol import iAPClient
from pypodcontrol.lingo import DisplayRemote, PlayState, RemoteEvent, TrackInfoType, Volume


@pytest.fixture
def transport():
    return FakeTransport()


@pytest.fixture
def dr(transport):
    with iAPClient(transport, timeout=0.5) as iap:
        yield iap.register(DisplayRemote)


def respond(transport, *payloads):
    """Inject the payloads whenever the accessory sends a packet"""

    transport.on_send = lambda payload: [transport.inject(p) for p in payloads]


def test_set_remote_event_notification(dr, transport):
    respond(transport, b"\x03\x00\x00\x08")  # iPodAck success
    dr.set_remote_event_notification([RemoteEvent.TRACK_INDEX, RemoteEvent.ABSOLUTE_VOLUME])

    assert transport.next_sent() == bytes.fromhex("03 08 00 01 00 02")


def test_event_listeners(dr, transport):
    received = []
    done = threading.Event()

    def listener(event, value):
        received.append((event, value))

    def any_listener(event, value):
        received.append(("any", event))
        if event == RemoteEvent.ABSOLUTE_VOLUME:
            done.set()

    dr.add_event_listener(RemoteEvent.TRACK_INDEX, listener)
    dr.add_event_listener(None, any_listener)
    dr.add_event_listener(RemoteEvent.ABSOLUTE_VOLUME, listener)

    transport.inject(bytes.fromhex("03 09 01 00 00 00 07"))
    transport.inject(bytes.fromhex("03 09 10 00 cf c8"))

    assert done.wait(1)
    assert received == [
        (RemoteEvent.TRACK_INDEX, 7),
        ("any", RemoteEvent.TRACK_INDEX),
        (RemoteEvent.ABSOLUTE_VOLUME, Volume(False, 0xCF, 0xC8)),
        ("any", RemoteEvent.ABSOLUTE_VOLUME),
    ]


@pytest.mark.parametrize(
    "event, data, value",
    [
        (RemoteEvent.TRACK_POSITION_MS, "00 01 00 00", 65536),
        (RemoteEvent.TRACK_POSITION_S, "00 0a", 10),
        (RemoteEvent.CHAPTER, "00 00 00 02 00 05 00 01", (2, 5, 1)),
        (RemoteEvent.PLAY_STATE, "02", PlayState.PAUSED),
        (RemoteEvent.VOLUME, "01 00", Volume(True, 0)),
        (RemoteEvent.HOLD_SWITCH, "01", True),
        (RemoteEvent.AUDIOBOOK_SPEED, "ff", -1),
        (RemoteEvent.DATE_TIME, "07 e9 0a 18 16 1e", datetime(2025, 10, 24, 22, 30)),
        (RemoteEvent.ALARM, "01 02 03", b"\x01\x02\x03"),
    ],
)
def test_decode_remote_event(event, data, value):
    assert DisplayRemote.decode_remote_event(event, bytes.fromhex(data)) == value


def test_get_play_status(dr, transport):
    respond(transport, bytes.fromhex("03 10 01 00 00 00 03 00 00 10 00 00 00 08 00"))
    status = dr.get_play_status()

    assert status.state == PlayState.PLAYING
    assert status.track_index == 3
    assert status.track_length_ms == 0x1000
    assert status.track_position_ms == 0x800


def test_get_track_text(dr, transport):
    respond(transport, b"\x03\x13\x05Exciting Moods for Cats\x00")

    assert dr.get_track_text(TrackInfoType.TITLE, 3) == "Exciting Moods for Cats"
    assert transport.next_sent() == bytes.fromhex("03 12 05 00 00 00 03 00 00")
