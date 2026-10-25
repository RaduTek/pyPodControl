import threading
from datetime import datetime

import pytest

from fake_transport import FakeTransport
from pypodcontrol import iAPAckError, iAPClient, iAPTimeoutError
from pypodcontrol.lingo import (
    AudiobookSpeed,
    ChapterInfo,
    DBCategory,
    ExtendedInterface,
    ExtendedPlayState,
    PixelFormat,
    PlayControlCommand,
    PlayerState,
    PlayingTrackInfoType,
    PlayStatusChange,
    PlayStatusEvent,
    ShuffleMode,
    TrackCapability,
    TrackCapsInfo,
    TrackIdentifierType,
    TrackInfoBit,
    iTunesInfoType,
)


@pytest.fixture
def transport():
    return FakeTransport()


@pytest.fixture
def iap(transport):
    with iAPClient(transport, timeout=0.5) as iap:
        yield iap


@pytest.fixture
def ei(iap):
    return iap.register(ExtendedInterface)


def respond(transport, *payloads):
    """Inject the payloads whenever the accessory sends a packet"""

    transport.on_send = lambda payload: [transport.inject(p) for p in payloads]


def respond_each(transport, *replies):
    """Inject the next reply (a payload or a list of payloads) for each sent packet"""

    pending = list(replies)

    def on_send(payload):
        if pending:
            reply = pending.pop(0)
            for p in reply if isinstance(reply, list) else [reply]:
                transport.inject(p)

    transport.on_send = on_send


def ack(command_id, status=0x00, transaction_id=None):
    tid = b"" if transaction_id is None else transaction_id.to_bytes(2, "big")
    return b"\x04\x00\x01" + tid + bytes([status]) + command_id.to_bytes(2, "big")


def record(index, name):
    return b"\x04\x00\x1b" + index.to_bytes(4, "big") + name.encode() + b"\x00"


def sent_all(transport):
    payloads = []
    while not transport.sent.empty():
        payloads.append(transport.sent.get())
    return payloads


# --- commands ---------------------------------------------------------------


@pytest.mark.parametrize(
    "call, sent",
    [
        (lambda ei: ei.select_db_record(DBCategory.ARTIST, 3), "04 00 17 02 00 00 00 03"),
        (lambda ei: ei.select_db_record(DBCategory.ALBUM, -1), "04 00 17 03 ff ff ff ff"),
        (lambda ei: ei.play_control(PlayControlCommand.NEXT), "04 00 29 08"),
        (lambda ei: ei.set_shuffle(ShuffleMode.TRACKS), "04 00 2e 01 01"),
        (lambda ei: ei.set_shuffle(ShuffleMode.OFF, restore_on_exit=None), "04 00 2e 00"),
        (lambda ei: ei.set_audiobook_speed(AudiobookSpeed.SLOWER, False), "04 00 0b ff 00"),
        (lambda ei: ei.reset_db_selection(), "04 00 16"),
        (lambda ei: ei.set_current_playing_track(7), "04 00 37 00 00 00 07"),
        (lambda ei: ei.play_prepared_uid_list(0x0102), "04 00 4b 00 00 00 00 00 00 00 01 02"),
    ],
)
def test_ack_commands(ei, transport, call, sent):
    expected = bytes.fromhex(sent)
    respond(transport, ack(int.from_bytes(expected[1:3], "big")))
    call(ei)

    assert transport.next_sent() == expected


def test_ack_error(ei, transport):
    respond(transport, ack(0x0029, 0x02))

    with pytest.raises(iAPAckError) as e:
        ei.play_control(PlayControlCommand.NEXT)

    assert e.value.status == 0x02


def test_get_play_status(ei, transport):
    respond(transport, bytes.fromhex("04 00 1d 00 00 10 00 00 00 08 00 02"))
    status = ei.get_play_status()

    assert (status.length_ms, status.position_ms, status.state) == (0x1000, 0x800, PlayerState.PAUSED)


def test_get_current_playing_track_index_none(ei, transport):
    respond(transport, bytes.fromhex("04 00 1f ff ff ff ff"))
    assert ei.get_current_playing_track_index() == -1


def test_get_track_title(ei, transport):
    respond(transport, b"\x04\x00\x21Exciting Moods for Cats\x00")

    assert ei.get_indexed_playing_track_title(3) == "Exciting Moods for Cats"
    assert transport.next_sent() == bytes.fromhex("04 00 20 00 00 00 03")


def test_get_chapter_info(ei, transport):
    respond(transport, bytes.fromhex("04 00 03 ff ff ff ff 00 00 00 00"))
    assert ei.get_current_playing_track_chapter_info() == ChapterInfo(-1, 0)


def test_get_track_caps(ei, transport):
    respond(transport, bytes.fromhex("04 00 0d 00 00 00 00 06 00 00 01 00 00 03"))
    info = ei.get_indexed_playing_track_info(PlayingTrackInfoType.CAPS, 2)

    assert info == TrackCapsInfo(TrackCapability.HAS_CHAPTERS | TrackCapability.HAS_ARTWORK, 0x100, 3)
    assert transport.next_sent() == bytes.fromhex("04 00 0c 00 00 00 00 02 00 00")


def test_get_track_release_date(ei, transport):
    respond(transport, bytes.fromhex("04 00 0d 02 1e 0f 16 18 0a 07 e9 05"))
    date = ei.get_indexed_playing_track_info(PlayingTrackInfoType.RELEASE_DATE, 0)

    assert date == datetime(2025, 10, 24, 22, 15, 30)


def test_get_track_artwork_count(ei, transport):
    respond(transport, bytes.fromhex("04 00 0d 07 00 01 00 02 00 05 00 01"))
    counts = ei.get_indexed_playing_track_info(PlayingTrackInfoType.ARTWORK_COUNT, 0)

    assert counts == {1: 2, 5: 1}


def test_get_track_lyrics_sections(ei, transport):
    respond(
        transport,
        b"\x04\x00\x0d\x04\x01\x00\x00La la ",
        b"\x04\x00\x0d\x04\x03\x00\x01la\x00",
    )

    assert ei.get_indexed_playing_track_info(PlayingTrackInfoType.LYRICS, 0) == "La la la"


def test_get_db_itunes_info(ei, transport):
    respond(transport, bytes.fromhex("04 00 3d 01 00 1e 0c 01 02 07 e8"))
    assert ei.get_db_itunes_info(iTunesInfoType.LAST_SYNC) == datetime(2024, 2, 1, 12, 30)


def test_get_color_display_image_limits(ei, transport):
    respond(transport, bytes.fromhex("04 00 3a 01 40 00 f0 03 01 40 00 f0 02"))
    limits = ei.get_color_display_image_limits()

    assert [(l.width, l.height, l.pixel_format) for l in limits] == [(320, 240, 3), (320, 240, 2)]


def test_genius_not_available(ei, transport):
    respond(transport, ack(0x0047, 0x12))
    assert not ei.is_genius_available_for_track(0x01, 4)


# --- mode -------------------------------------------------------------------


def test_enter_extended_mode(ei, transport):
    respond(transport, bytes.fromhex("00 02 00 37"))
    ei.enter_extended_mode()

    assert transport.next_sent() == bytes.fromhex("00 37 01")


def test_enter_extended_mode_falls_back(ei, transport):
    respond_each(transport, bytes.fromhex("00 02 04 37"), bytes.fromhex("00 02 00 05"))
    ei.enter_extended_mode()

    assert transport.next_sent() == bytes.fromhex("00 37 01")
    assert transport.next_sent() == bytes.fromhex("00 05")


# --- multiple responses -----------------------------------------------------


def test_retrieve_records_by_count(ei, transport):
    respond(transport, record(0, "Rock"), record(1, "Jazz"), record(2, "Ska"))
    records = ei.retrieve_categorized_database_records(DBCategory.GENRE, 0, 3)

    assert records == [(0, "Rock"), (1, "Jazz"), (2, "Ska")]
    assert transport.next_sent() == bytes.fromhex("04 00 1a 04 00 00 00 00 00 00 00 03")


def test_retrieve_all_records_ends_when_idle(ei, transport):
    respond(transport, record(0, "Rock"), record(1, "Jazz"))
    records = ei.retrieve_categorized_database_records(DBCategory.GENRE, idle_timeout=0.1)

    assert records == [(0, "Rock"), (1, "Jazz")]
    assert transport.next_sent() == bytes.fromhex("04 00 1a 04 00 00 00 00 ff ff ff ff")


def test_retrieve_records_error(ei, transport):
    respond(transport, ack(0x001A, 0x04))

    with pytest.raises(iAPAckError):
        ei.retrieve_categorized_database_records(DBCategory.GENRE)


def test_retrieve_records_timeout(ei):
    with pytest.raises(iAPTimeoutError):
        ei.retrieve_categorized_database_records(DBCategory.GENRE)


def test_track_info_mask():
    encode = ExtendedInterface.encode_track_info_mask

    assert encode([TrackInfoBit.UID]) == b"\x80"
    assert encode([TrackInfoBit.CAPABILITIES, TrackInfoBit.LYRICS]) == b"\x01\x08"
    assert encode([TrackInfoBit.START_STOP_OFFSET]) == b"\x00\x00\x00\x08"


def test_get_db_track_info(ei, transport):
    def info(index, bit, data):
        return b"\x04\x00\x41" + index.to_bytes(4, "big") + bytes([bit]) + data

    respond(
        transport,
        info(5, 1, b"One\x00"),
        info(5, 6, (180000).to_bytes(4, "big")),
        info(6, 1, b"Two\x00"),
        info(6, 6, (200000).to_bytes(4, "big")),
    )
    tracks = ei.get_db_track_info(5, 2, [TrackInfoBit.NAME, TrackInfoBit.DURATION])

    assert tracks == {
        5: {TrackInfoBit.NAME: "One", TrackInfoBit.DURATION: 180000},
        6: {TrackInfoBit.NAME: "Two", TrackInfoBit.DURATION: 200000},
    }
    assert transport.next_sent() == bytes.fromhex("04 00 40 00 00 00 05 00 00 00 02 42")


def test_get_pb_track_info_multi_packet(ei, transport):
    def info(bit, data):
        return b"\x04\x00\x43\x00\x00\x00\x00" + bytes([bit]) + data

    respond(
        transport,
        info(10, b"\x00\x00Intro\x00"),
        info(10, b"\x00\x01Outro\x00"),
        info(11, b"\x00\x01\x00\x01la la\x00"),
        info(11, b"\x00\x00\x00\x01La la "),
    )
    tracks = ei.get_pb_track_info(
        0, 1, [TrackInfoBit.CHAPTER_NAMES, TrackInfoBit.LYRICS], idle_timeout=0.1
    )

    assert tracks[0] == {
        TrackInfoBit.CHAPTER_NAMES: [(0, "Intro"), (1, "Outro")],
        TrackInfoBit.LYRICS: "La la la la",
    }


@pytest.mark.parametrize(
    "bit, data, value",
    [
        (TrackInfoBit.CAPABILITIES, "00 00 00 81", TrackCapability.AUDIOBOOK | TrackCapability.VIDEO),
        (TrackInfoBit.UID, "00 00 00 00 00 00 01 02", 0x0102),
        (TrackInfoBit.CHAPTER_TIMES, "00 00 00 00 00 00 00 01 00 00 10 00", [(0, 0), (1, 0x1000)]),
        (TrackInfoBit.LAST_PLAYED, "00 00 00 00 00 00 00", None),
        (TrackInfoBit.STAR_RATING, "3c", 60),
        (TrackInfoBit.VOLUME_ADJUST, "9c", -100),
        (TrackInfoBit.START_STOP_OFFSET, "00 00 00 01 00 00 00 02", (1, 2)),
    ],
)
def test_decode_track_info(bit, data, value):
    assert ExtendedInterface.decode_track_info(bit, bytes.fromhex(data)) == value


# --- artwork ----------------------------------------------------------------


def artwork_descriptor(pixel_format, width, height, row_size):
    return (
        bytes([pixel_format])
        + width.to_bytes(2, "big")
        + height.to_bytes(2, "big")
        + bytes.fromhex("00 00 00 00")
        + (width - 1).to_bytes(2, "big")
        + (height - 1).to_bytes(2, "big")
        + row_size.to_bytes(4, "big")
    )


def test_get_artwork_formats(ei, transport):
    respond(transport, bytes.fromhex("04 00 0f 00 01 02 00 64 00 64 00 02 02 00 32 00 32"))
    formats = ei.get_artwork_formats()

    assert [(f.format_id, f.width, f.height) for f in formats] == [(1, 100, 100), (2, 50, 50)]


def test_get_track_artwork_data(ei, transport):
    # 2x2 RGB565, 4 byte rows, split over 3 packets
    pixels = bytes(range(8))
    respond(
        transport,
        b"\x04\x00\x11\x00\x00" + artwork_descriptor(2, 2, 2, 4) + pixels[:3],
        b"\x04\x00\x11\x00\x01" + pixels[3:6],
        b"\x04\x00\x11\x00\x02" + pixels[6:],
    )
    artwork = ei.get_track_artwork_data(1, 2, 0)

    assert (artwork.pixel_format, artwork.width, artwork.height) == (2, 2, 2)
    assert artwork.inset == (0, 0, 1, 1)
    assert artwork.row_size == 4
    assert artwork.data == pixels


def test_get_artwork_data_multisection(ei, transport):
    pixels = bytes(range(8))
    payload = b"\x01" + (3).to_bytes(4, "big") + artwork_descriptor(2, 2, 2, 4) + pixels
    respond(
        transport,
        b"\x04\x00\x4f\x00\x00\x00\x01" + payload[:10],
        b"\x04\x00\x4f\x00\x01\x00\x01" + payload[10:],
    )
    artwork = ei.get_artwork_data(TrackIdentifierType.PLAYBACK_INDEX, 3, 2, 0)

    assert artwork.data == pixels
    assert transport.next_sent() == bytes.fromhex("04 00 4e 01 00 00 00 03 00 02 00 00 00 00")


def test_get_artwork_times(ei, transport):
    respond(
        transport,
        bytes.fromhex("04 00 4d 00 00 00 00 00 00 00 00 07 00 00 00 00 00 00 03 e8"),
    )
    times = ei.get_artwork_times(TrackIdentifierType.UID, 7, 1)

    assert times == [0, 1000]


# --- multisection and chunked sends -----------------------------------------


def test_prepare_uid_list_sections(ei, transport):
    ei._max_payload = 25  # 2 UIDs per section
    respond_each(transport, ack(0x004A, 0x13), ack(0x004A, 0x13), ack(0x004A))
    ei.prepare_uid_list([1, 2, 3, 4, 5])

    sections = [transport.next_sent() for _ in range(3)]
    assert [s[3:7] for s in sections] == [
        bytes.fromhex("00 00 00 02"),
        bytes.fromhex("00 01 00 02"),
        bytes.fromhex("00 02 00 02"),
    ]
    assert [len(s) for s in sections] == [7 + 16, 7 + 16, 7 + 8]


def test_prepare_uid_list_shares_transaction_id(iap, ei, transport):
    iap.transaction_ids_enabled = True
    ei._max_payload = 27

    def on_send(payload):
        tid = int.from_bytes(payload[3:5], "big")
        last = payload[5:7] == payload[7:9]
        transport.inject(ack(0x004A, 0x00 if last else 0x13, transaction_id=tid))

    transport.on_send = on_send
    ei.prepare_uid_list([1, 2, 3])

    sections = sent_all(transport)
    assert len(sections) == 2
    assert sections[0][3:5] == sections[1][3:5]


def test_prepare_uid_list_section_error(ei, transport):
    ei._max_payload = 25
    respond_each(transport, ack(0x004A, 0x04))

    with pytest.raises(iAPAckError):
        ei.prepare_uid_list([1, 2, 3])


def test_set_display_image_data_chunks(ei, transport):
    ei._max_payload = 20  # 15 bytes of data per packet after the index
    respond(transport, ack(0x0032))
    data = bytes(range(24))  # 4x3 RGB565, 8 byte rows
    ei.set_display_image_data(PixelFormat.RGB565_LE, 4, 3, data)

    packets = sent_all(transport)
    assert packets[0] == bytes.fromhex("04 00 32 00 00 02 00 04 00 03 00 00 00 08") + data[:6]
    assert packets[1] == bytes.fromhex("04 00 32 00 01") + data[6:21]
    assert packets[2] == bytes.fromhex("04 00 32 00 02") + data[21:]


def test_set_display_image_data_too_short(ei):
    with pytest.raises(ValueError):
        ei.set_display_image_data(PixelFormat.MONO_2BPP, 16, 2, b"\x00" * 4)


# --- notifications ----------------------------------------------------------


def test_set_play_status_change_notification(ei, transport):
    respond(transport, ack(0x0026))
    assert ei.set_play_status_change_notification(
        [PlayStatusEvent.TRACK_INDEX, PlayStatusEvent.TRACK_TIME_S]
    )

    assert transport.next_sent() == bytes.fromhex("04 00 26 00 00 00 14")


def test_play_status_change_notification_fallback(ei, transport):
    respond_each(transport, ack(0x0026, 0x04), ack(0x0026))
    assert not ei.set_play_status_change_notification([PlayStatusEvent.TRACK_INDEX])

    assert transport.next_sent() == bytes.fromhex("04 00 26 00 00 00 04")
    assert transport.next_sent() == bytes.fromhex("04 00 26 01")


def test_event_listeners(ei, transport):
    received = []
    done = threading.Event()

    def listener(change, value):
        received.append((change, value))

    def any_listener(change, value):
        received.append(("any", change))
        if change == PlayStatusChange.PLAYBACK_STATUS_EXTENDED:
            done.set()

    ei.add_event_listener(PlayStatusChange.TRACK_INDEX, listener)
    ei.add_event_listener(None, any_listener)

    transport.inject(bytes.fromhex("04 00 27 01 00 00 00 05"))
    transport.inject(bytes.fromhex("04 00 27 06 0a"))

    assert done.wait(1)
    assert received == [
        (PlayStatusChange.TRACK_INDEX, 5),
        ("any", PlayStatusChange.TRACK_INDEX),
        ("any", PlayStatusChange.PLAYBACK_STATUS_EXTENDED),
    ]


@pytest.mark.parametrize(
    "change, data, value",
    [
        (PlayStatusChange.PLAYBACK_STOPPED, "", None),
        (PlayStatusChange.TRACK_INDEX, "ff ff ff ff", -1),
        (PlayStatusChange.TRACK_TIME_MS, "00 01 00 00", 65536),
        (PlayStatusChange.PLAYBACK_STATUS_EXTENDED, "0b", ExtendedPlayState.PAUSED),
        (PlayStatusChange.TRACK_UID, "00 00 00 00 00 00 00 2a", 42),
        (PlayStatusChange.TRACK_CAPABILITIES, "00 00 00 01", TrackCapability.AUDIOBOOK),
        (PlayStatusChange.PLAYBACK_ENGINE_CONTENTS, "00 00 00 0c", 12),
    ],
)
def test_decode_play_status_change(change, data, value):
    assert ExtendedInterface.decode_play_status_change(change, bytes.fromhex(data)) == value


def test_set_display_image_scales_to_limits(ei, transport):
    Image = pytest.importorskip("PIL.Image")
    ei._max_payload = 500
    respond_each(transport, bytes.fromhex("04 00 3a 00 02 00 02 02"), ack(0x0032))
    ei.set_display_image(Image.new("RGB", (4, 4), (255, 0, 0)))

    assert transport.next_sent() == bytes.fromhex("04 00 39")
    assert transport.next_sent() == (
        bytes.fromhex("04 00 32 00 00 02 00 02 00 02 00 00 00 04") + bytes.fromhex("00 f8") * 4
    )
