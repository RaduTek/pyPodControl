import pytest

from pypodcontrol.packet import (
    Packet,
    PacketParser,
    checksum,
    encode_frame,
)


def test_checksum_wraps_to_zero():
    assert checksum(b"\x80\x80") == 0x00
    assert checksum(b"\x03\x00\x01\x02") == 0xFA


def test_encode_identify_simple_remote():
    payload = Packet(0x00, 0x01, b"\x02").to_payload()
    assert encode_frame(payload) == bytes.fromhex("55 03 00 01 02 FA")


def test_encode_extended_command_with_transaction_id():
    packet = Packet(0x04, 0x0012, b"", transaction_id=0x0102)
    assert packet.to_payload(extended_command=True) == bytes.fromhex("04 00 12 01 02")


def test_large_frame_threshold():
    assert encode_frame(b"\x00" * 252)[1] == 252
    assert encode_frame(b"\x00" * 253)[1:4] == bytes.fromhex("00 00 FD")

    with pytest.raises(ValueError):
        encode_frame(b"\x00" * 0x10000)


@pytest.mark.parametrize("extended", [False, True])
@pytest.mark.parametrize("transaction_id", [None, 0xBEEF])
def test_payload_roundtrip(extended, transaction_id):
    packet = Packet(0x04, 0x0102 if extended else 0x02, b"abc", transaction_id)
    payload = packet.to_payload(extended)
    decoded = Packet.from_payload(payload, extended, transaction_id is not None)
    assert decoded == packet


def test_from_payload_too_short():
    with pytest.raises(ValueError):
        Packet.from_payload(b"\x04\x00", extended_command=True, has_transaction_id=True)


def test_parser_skips_sync_and_padding():
    frame = encode_frame(b"\x00\x02\x00\x01")
    parser = PacketParser()
    assert parser.feed(b"\xff" + frame + b"\x00\x00\x00") == [b"\x00\x02\x00\x01"]
    assert not parser.in_packet


def test_parser_split_chunks():
    frames = encode_frame(b"\x00\x08abc") + encode_frame(b"\x02\x01\x00\x00")
    parser = PacketParser()
    payloads = []
    for i in range(len(frames)):
        payloads += parser.feed(frames[i : i + 1])
    assert payloads == [b"\x00\x08abc", b"\x02\x01\x00\x00"]


def test_parser_large_frame():
    payload = b"\x04\x00\x11" + bytes(range(256)) * 2
    parser = PacketParser()
    assert parser.feed(b"\xff" + encode_frame(payload)) == [payload]


def test_parser_drops_bad_checksum_and_resyncs():
    bad = bytearray(encode_frame(b"\x00\x02\x00\x01"))
    bad[-1] ^= 0xFF
    good = encode_frame(b"\x00\x08abc")
    parser = PacketParser()
    assert parser.feed(bytes(bad) + good) == [b"\x00\x08abc"]


def test_parser_reset_discards_partial():
    frame = encode_frame(b"\x00\x08abc")
    parser = PacketParser()
    assert parser.feed(frame[:3]) == []
    assert parser.in_packet
    parser.reset()
    assert parser.feed(frame) == [b"\x00\x08abc"]
