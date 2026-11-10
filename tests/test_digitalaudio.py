import threading

import pytest

from fake_transport import FakeTransport
from pypodcontrol import iAPClient
from pypodcontrol.lingo import DigitalAudio, TrackAttributes


@pytest.fixture
def transport():
    return FakeTransport()


@pytest.fixture
def da(transport):
    with iAPClient(transport, timeout=0.5) as iap:
        yield iap.register(DigitalAudio)


def test_default_sample_rate_caps(transport):
    with iAPClient(transport, timeout=0.5) as iap:
        iap.register(DigitalAudio())

        transport.inject(bytes.fromhex("0a 02"))  # GetAccessorySampleRateCaps

        payload = transport.next_sent()
        assert payload[:2] == bytes.fromhex("0a 03")  # RetAccessorySampleRateCaps
        # Default caps include 44100 and 48000 Hz, as concatenated 32-bit values
        assert bytes.fromhex("0000ac44") in payload
        assert bytes.fromhex("0000bb80") in payload


def test_custom_sample_rate_caps(transport):
    with iAPClient(transport, timeout=0.5) as iap:
        iap.register(DigitalAudio([44100]))

        transport.inject(bytes.fromhex("0a 02"))

        assert transport.next_sent() == bytes.fromhex("0a 03 00 00 ac 44")


def test_track_new_audio_attributes(da, transport):
    received = []
    done = threading.Event()

    def listener(attributes):
        received.append(attributes)
        done.set()

    da.add_track_attributes_listener(listener)

    # TrackNewAudioAttributes: 44100 Hz + two sound check bytes
    transport.inject(bytes.fromhex("0a 04 00 00 ac 44 01 02"))

    # Accessory acknowledges the command
    assert transport.next_sent() == bytes.fromhex("0a 00 00 04")

    assert done.wait(1)
    assert received == [TrackAttributes(44100, b"\x01\x02")]
    assert da.sample_rate == 44100


def test_set_video_delay_is_acked(da, transport):
    transport.inject(bytes.fromhex("0a 05 00 00 00 64"))  # SetVideoDelay 100 ms

    assert transport.next_sent() == bytes.fromhex("0a 00 00 05")


def test_close_resets_state_on_client_close(transport):
    iap = iAPClient(transport, timeout=0.5)
    iap.open()
    da = iap.register(DigitalAudio)
    da.add_track_attributes_listener(lambda attributes: None)

    transport.inject(bytes.fromhex("0a 04 00 00 ac 44"))
    transport.next_sent()  # ack, so the rate is set by now
    assert da.sample_rate == 44100

    iap.close()

    assert da.sample_rate is None
    assert da._attributes_listeners == []


def test_close_resets_state_on_unregister(da):
    da.add_track_attributes_listener(lambda attributes: None)
    da.sample_rate = 44100

    da.iap.unregister(DigitalAudio)

    assert da.sample_rate is None
    assert da._attributes_listeners == []
