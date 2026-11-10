import hashlib

import pytest

from fake_transport import FakeTransport
from test_identify import FakeiPod
from pypodcontrol import CoprocessorError, iAPClient
from pypodcontrol.auth import (
    AuthenticationProvider,
    CoprocessorAuthenticationProvider,
    I2CBus,
    I2CNackError,
)
from pypodcontrol.lingo import SimpleRemote

CERT = bytes(range(256)) * 3 + bytes(177)  # 945 bytes


class FakeCoprocessorBus(I2CBus):
    """Emulates the register map of a CP 2.0C"""

    def __init__(self, address=0x10, nacks=0, polls_before_done=0, error=None):
        self.address = address
        self.nacks = nacks
        self.polls_before_done = polls_before_done
        self.error = error  # error code to raise on sign
        self.version = 0x05
        self.challenge = b""
        self.sig_len_written = None
        self.status = 0
        self.error_reg = 0
        self.pos = 0
        self.signature = b""
        self.polls = 0
        self.closed = False
        self.pointer_writes = 0
        self.read_nacks = 0

    def _check(self, address):
        if address != self.address:
            raise I2CNackError("wrong address")
        if self.nacks:
            self.nacks -= 1
            raise I2CNackError("busy")

    def _stream(self, reg):
        if reg == 0x00:
            return bytes([self.version, 1, 2, 0]) + (0x200).to_bytes(4, "big")
        if reg == 0x02:
            return bytes([2, 0]) + (0x200).to_bytes(4, "big")
        if reg == 0x04:
            return (0x200).to_bytes(4, "big")
        if reg == 0x05:
            code, self.error_reg = self.error_reg, 0
            return bytes([code])
        if reg == 0x10:
            if self.status == 0x10 and self.polls < self.polls_before_done:
                self.polls += 1
                return b"\x00"
            return bytes([self.status])
        if reg == 0x11:
            return len(self.signature).to_bytes(2, "big") + self.signature
        if reg == 0x12:
            return self.signature
        if reg == 0x30:
            return len(CERT).to_bytes(2, "big")
        if reg == 0x31:
            return CERT
        return b""

    def write(self, address, data):
        self._check(address)
        reg, payload = data[0], data[1:]
        if not payload:  # register pointer for a following read
            self.pointer_writes += 1
            self._buf = self._stream(reg)
            self.pos = 0
            return
        if reg == 0x20:
            n = int.from_bytes(payload[:2], "big")
            self.challenge = payload[2 : 2 + n]
        elif reg == 0x11:
            self.sig_len_written = int.from_bytes(payload[:2], "big")
        elif reg == 0x10 and payload[0] == 1:
            if self.error is not None:
                self.status = 0x80
                self.error_reg = self.error
            else:
                self.signature = hashlib.sha1(self.challenge).digest() * 6
                self.signature = self.signature[:120]
                self.status = 0x10

    def write_read(self, address, data, length):
        self._check(address)
        self._buf = self._stream(data[0])
        self.pos = 0
        return self.read(address, length, _checked=True)

    def read(self, address, length, _checked=False):
        if not _checked:
            self._check(address)
            if self.read_nacks:
                self.read_nacks -= 1
                raise I2CNackError("busy after register write")
        chunk = self._buf[self.pos : self.pos + length]
        self.pos += length
        return chunk + b"\xff" * (length - len(chunk))

    def close(self):
        self.closed = True


def test_is_authentication_provider():
    assert isinstance(CoprocessorAuthenticationProvider(FakeCoprocessorBus()), AuthenticationProvider)


def test_chip_info():
    provider = CoprocessorAuthenticationProvider(FakeCoprocessorBus())
    assert provider.protocol_version == (2, 0)
    assert provider.device_id == 0x200


def test_wrong_device_version():
    bus = FakeCoprocessorBus()
    bus.version = 0x03
    with pytest.raises(CoprocessorError, match="0x03"):
        CoprocessorAuthenticationProvider(bus).device_id


def test_certificate_streamed_and_cached():
    bus = FakeCoprocessorBus()
    provider = CoprocessorAuthenticationProvider(bus)
    assert provider.get_certificate() == CERT
    bus.nacks = 10**6  # any further bus access would fail
    assert provider.get_certificate() == CERT


def test_sign_challenge():
    bus = FakeCoprocessorBus(polls_before_done=3)
    provider = CoprocessorAuthenticationProvider(bus)
    challenge = bytes(range(20))

    sig = provider.sign_challenge(challenge)

    assert bus.challenge == challenge
    assert bus.sig_len_written == 128
    assert sig == bus.signature and len(sig) == 120


def test_invalid_challenge_length():
    provider = CoprocessorAuthenticationProvider(FakeCoprocessorBus())
    with pytest.raises(ValueError):
        provider.sign_challenge(b"")
    with pytest.raises(ValueError):
        provider.sign_challenge(bytes(129))


def test_nack_retry_succeeds():
    bus = FakeCoprocessorBus(nacks=5)
    assert CoprocessorAuthenticationProvider(bus).device_id == 0x200


def test_nack_timeout():
    bus = FakeCoprocessorBus(nacks=10**6)
    provider = CoprocessorAuthenticationProvider(bus, busy_timeout=0.05)
    with pytest.raises(CoprocessorError, match="busy"):
        provider.device_id


def test_alternate_address():
    bus = FakeCoprocessorBus(address=0x11)
    assert CoprocessorAuthenticationProvider(bus, address=0x11).device_id == 0x200


def test_sign_error_reported():
    bus = FakeCoprocessorBus(error=0x04)
    provider = CoprocessorAuthenticationProvider(bus)
    with pytest.raises(CoprocessorError, match="Invalid challenge length") as exc:
        provider.sign_challenge(bytes(20))
    assert exc.value.code == 0x04


def test_sign_timeout():
    bus = FakeCoprocessorBus(polls_before_done=10**9)
    provider = CoprocessorAuthenticationProvider(bus, process_timeout=0.05)
    with pytest.raises(CoprocessorError, match="Timed out"):
        provider.sign_challenge(bytes(20))


def test_close():
    bus = FakeCoprocessorBus()
    with CoprocessorAuthenticationProvider(bus):
        pass
    assert bus.closed


def test_authentication_handshake():
    transport = FakeTransport()
    ipod = FakeiPod(transport, idps=False)
    bus = FakeCoprocessorBus(polls_before_done=2)
    provider = CoprocessorAuthenticationProvider(bus)

    with iAPClient(transport, auth=provider, timeout=0.5) as iap:
        iap.register(SimpleRemote)
        iap.start_identify()
        assert iap.is_identified
        assert iap.general.authentication_status == 0x00

    assert bytes(ipod.certificate) == CERT
    assert ipod.signature == bus.signature


def test_read_nack_retries_only_the_read():
    bus = FakeCoprocessorBus()
    bus.read_nacks = 5
    assert CoprocessorAuthenticationProvider(bus).device_id == 0x200
    # The register pointer is not rewritten on every NACKed read
    assert bus.pointer_writes == 3  # version, protocol, device ID
