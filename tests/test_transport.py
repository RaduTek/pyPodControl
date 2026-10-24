import threading

import pytest

from fake_transport import FakeTransport
from pypodcontrol.errors import TransportError
from pypodcontrol.transport import UARTTransport


class FakeSerial:
    def __init__(self) -> None:
        self.port = "fake"
        self.is_open = True
        self.timeout = None
        self.in_waiting = 0
        self.written = b""

    def write(self, data: bytes) -> int:
        self.written += data
        return len(data)

    def read(self, size: int) -> bytes:
        return b""

    def close(self) -> None:
        self.is_open = False


def test_uart_identify_bytes():
    serial = FakeSerial()
    transport = UARTTransport(serial)
    transport.open()
    transport.send(b"\x00\x01\x02")
    transport.close()

    assert serial.written == bytes.fromhex("FF 55 03 00 01 02 FA")
    assert not serial.is_open


def test_uart_wake_sends_sync_byte():
    serial = FakeSerial()
    transport = UARTTransport(serial)
    transport.wake_delay = 0
    transport.wake()
    assert serial.written == b"\xff"


def test_send_requires_open():
    with pytest.raises(TransportError):
        FakeTransport().send(b"\x00\x01")


def test_reader_delivers_payloads():
    received = []
    done = threading.Event()

    def receiver(payload: bytes) -> None:
        received.append(payload)
        if len(received) == 2:
            done.set()

    transport = FakeTransport()
    transport.set_receiver(receiver)

    with transport:
        transport.inject(b"\x00\x08abc")
        transport.inject(b"\x02\x01\x00\x00")
        assert done.wait(1)

    assert received == [b"\x00\x08abc", b"\x02\x01\x00\x00"]


def test_receiver_errors_do_not_stop_reader():
    received = threading.Event()
    calls = []

    def receiver(payload: bytes) -> None:
        calls.append(payload)
        if len(calls) == 1:
            raise RuntimeError("boom")
        received.set()

    transport = FakeTransport()
    transport.set_receiver(receiver)

    with transport:
        transport.inject(b"\x00\x08a")
        transport.inject(b"\x00\x08b")
        assert received.wait(1)


def test_reader_closes_on_read_error():
    import threading

    closed = threading.Event()

    class FailingTransport(FakeTransport):
        def _read_chunk(self):
            raise OSError("device disconnected")

        def _close(self):
            closed.set()

    transport = FailingTransport()
    transport.open()

    # The reader hits the error, stops and releases the link on its own
    assert closed.wait(1)
    assert not transport.is_open

    transport.close()  # idempotent, must not raise
