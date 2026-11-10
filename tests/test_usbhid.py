import pytest

from pypodcontrol.errors import TransportError
from pypodcontrol.packet import PacketParser, encode_frame
from pypodcontrol.transport import usbhid
from pypodcontrol.transport.usbhid import (
    USBHIDTransport,
    pack_reports,
    parse_report_descriptor,
)

# Vendor page, ID 1: 12 byte input; ID 2: 64 byte input; ID 3: 8 byte output; ID 4: 64 byte output
DESCRIPTOR = bytes.fromhex(
    "06 00 FF"  # Usage Page (Vendor 0xFF00)
    "09 01"  # Usage
    "A1 01"  # Collection (Application)
    "75 08"  # Report Size 8
    "85 01 95 0C 09 01 81 02"  # ID 1, Count 12, Input
    "85 02 95 40 09 01 81 02"  # ID 2, Count 64, Input
    "85 03 95 08 09 01 91 02"  # ID 3, Count 8, Output
    "85 04 96 40 00 09 01 91 02"  # ID 4, Count 64 (2 byte item), Output
    "C0"  # End Collection
)


def test_parse_report_descriptor():
    inputs, outputs = parse_report_descriptor(DESCRIPTOR)
    assert inputs == {1: 12, 2: 64}
    assert outputs == {3: 8, 4: 64}


def test_pack_small_frame_uses_smallest_report():
    frame = encode_frame(b"\x00\x07")
    reports = pack_reports(frame, {3: 8, 4: 64})
    assert reports == [bytes([3, 0x00]) + frame + bytes(7 - len(frame))]


def test_pack_large_frame_across_reports():
    frame = encode_frame(bytes(range(256)) * 2 + b"\x00" * 88)
    outputs = {3: 8, 4: 64}
    reports = pack_reports(frame, outputs)

    assert all(len(r) == outputs[r[0]] + 1 for r in reports)
    assert reports[0][1] == 0x02
    assert all(r[1] == 0x03 for r in reports[1:-1])
    assert reports[-1][1] == 0x01

    parser = PacketParser()
    payloads = []
    for report in reports:
        payloads += parser.feed(report[2:])
    assert payloads == [frame[4:-1]]


class FakeHIDDevice:
    def __init__(self, reports):
        self.reports = list(reports)
        self.written = []

    def open_path(self, path):
        self.path = path

    def get_report_descriptor(self):
        return list(DESCRIPTOR)

    def read(self, size, timeout_ms=0):
        return list(self.reports.pop(0)) if self.reports else []

    def write(self, data):
        self.written.append(bytes(data))
        return len(data)

    def close(self):
        pass


class FakeHID:
    def __init__(self, device):
        self._device = device

    def enumerate(self, vendor_id, product_id):
        devices = [
            {"path": b"keyboard", "product_id": 0x0250},
            {"path": b"fake", "product_id": 0x1261},
        ]
        return [d for d in devices if product_id in (0, d["product_id"])]

    def device(self):
        return self._device


def test_transport_roundtrip(monkeypatch):
    frame = encode_frame(b"\x00\x08iPod\x00")
    stale = encode_frame(b"\x00\x08" + b"x" * 20)
    incoming = [
        # Partial packet whose set never completes, flushed by the next set
        bytes([1, 0x02]) + stale[:11],
        bytes([2, 0x00]) + frame + bytes(64 - 1 - len(frame)),
    ]
    device = FakeHIDDevice(incoming)
    monkeypatch.setattr(usbhid, "hid", FakeHID(device))

    transport = USBHIDTransport()
    transport._open()
    assert device.path == b"fake"
    assert transport.output_reports == {3: 8, 4: 64}

    assert transport.parser.feed(transport._read_chunk()) == []
    assert transport.parser.in_packet

    chunk = transport._read_chunk()
    assert not transport.parser.in_packet
    assert transport.parser.feed(chunk) == [b"\x00\x08iPod\x00"]

    transport._running.set()
    transport.send(b"\x00\x07")
    assert device.written == [bytes([3, 0x00]) + encode_frame(b"\x00\x07") + bytes(2)]


def test_missing_hidapi(monkeypatch):
    monkeypatch.setattr(usbhid, "hid", None)
    with pytest.raises(TransportError):
        USBHIDTransport()
