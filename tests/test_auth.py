import threading

import pytest

from fake_transport import FakeTransport
from test_identify import FakeiPod
from pypodcontrol import iAPClient, iAPIdentificationError
from pypodcontrol.auth import AuthenticationProvider, BypassedAuthenticationProvider
from pypodcontrol.auth.bypassed import DEFAULT_CERTIFICATE_PATH
from pypodcontrol.lingo import SimpleRemote


def test_provider_defaults():
    provider = BypassedAuthenticationProvider()

    assert provider.device_id == 0x200
    assert provider.protocol_version == (2, 0)
    assert provider.certificate_path == DEFAULT_CERTIFICATE_PATH
    assert len(provider.get_certificate()) == 945
    assert provider.sign_challenge(bytes(20)) == bytes(128)


def test_provider_is_authentication_provider():
    assert isinstance(BypassedAuthenticationProvider(), AuthenticationProvider)


def test_provider_custom_arguments(tmp_path):
    cert = tmp_path / "cert.bin"
    cert.write_bytes(b"hello")
    provider = BypassedAuthenticationProvider(cert, device_id=0x1234, signature_length=64)

    assert provider.device_id == 0x1234
    assert provider.get_certificate() == b"hello"
    assert provider.sign_challenge(b"") == bytes(64)


def test_certificate_cached(tmp_path):
    cert = tmp_path / "cert.bin"
    cert.write_bytes(b"first")
    provider = BypassedAuthenticationProvider(cert)
    assert provider.get_certificate() == b"first"

    cert.write_bytes(b"second")
    assert provider.get_certificate() == b"first"


def test_authentication_handshake_multi_section():
    transport = FakeTransport()
    ipod = FakeiPod(transport, idps=False)
    provider = BypassedAuthenticationProvider()

    with iAPClient(transport, auth=provider, timeout=0.5) as iap:
        iap.register(SimpleRemote)
        iap.start_identify()

        assert iap.is_identified
        assert iap.general.authentication_status == 0x00

    # The 945 byte certificate is reassembled from its 500 byte sections
    assert bytes(ipod.certificate) == provider.get_certificate()
    assert ipod.signature == bytes(128)

    # Certificate sections, then the signature
    assert [p[1] for p in ipod.received].count(0x15) == 2
    assert [p[1] for p in ipod.received].count(0x18) == 1


def test_authentication_failure_raises():
    transport = FakeTransport()
    FakeiPod(transport, idps=False, auth_status=0x0A)  # certificate invalid

    with iAPClient(transport, auth=BypassedAuthenticationProvider(), timeout=0.5) as iap:
        with pytest.raises(iAPIdentificationError, match="0x0A"):
            iap.start_identify()

        assert not iap.is_identified


def test_authentication_timeout_raises():
    transport = FakeTransport()
    FakeiPod(transport, idps=False, drive_auth=False)  # iPod never authenticates

    with iAPClient(transport, auth=BypassedAuthenticationProvider(), timeout=0.2) as iap:
        with pytest.raises(iAPIdentificationError, match="timed out"):
            iap.start_identify(auth_timeout=0.3)


def test_authentication_over_idps():
    transport = FakeTransport()
    ipod = FakeiPod(transport, idps=True)
    provider = BypassedAuthenticationProvider()

    with iAPClient(transport, auth=provider, use_idps=True, timeout=0.5) as iap:
        iap.start_identify()

        assert iap.is_identified
        assert iap.general.authentication_status == 0x00

    assert bytes(ipod.certificate) == provider.get_certificate()
    assert ipod.signature == bytes(128)


def test_no_provider_ignores_auth_request():
    transport = FakeTransport()
    ipod = FakeiPod(transport, idps=False, drive_auth=False)

    with iAPClient(transport, timeout=0.5) as iap:
        iap.register(SimpleRemote)
        iap.start_identify()

        done = threading.Event()
        transport.on_send = lambda p: done.set()

        # An unsolicited auth request without a provider is ignored, not answered
        transport.inject(b"\x00\x14")
        assert not done.wait(0.3)
