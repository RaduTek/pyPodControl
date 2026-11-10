import json
import subprocess

import pytest

from pypodcontrol.audio import AudioError, PipeWireRouter, create_audio_router
from pypodcontrol.audio import pipewire


PW_DUMP = [
    {
        "id": 10,
        "type": "PipeWire:Interface:Metadata",
        "metadata": [
            {"key": "default.audio.sink", "value": {"name": "alsa_output.pci-0000_00.analog"}},
        ],
    },
    {
        "id": 42,
        "type": "PipeWire:Interface:Node",
        "info": {
            "props": {
                "media.class": "Audio/Source",
                "node.name": "alsa_input.usb-Apple_iPod-00.analog-stereo",
                "node.description": "iPod",
            }
        },
    },
    {
        "id": 7,
        "type": "PipeWire:Interface:Node",
        "info": {"props": {"media.class": "Audio/Sink", "node.name": "some-other-sink"}},
    },
]


class FakeRun:
    """Records subprocess calls and returns canned pw-dump output"""

    def __init__(self, dump=PW_DUMP):
        self.calls = []
        self.dump = dump

    def __call__(self, args, capture_output=False, text=False):
        self.calls.append(args)
        stdout = json.dumps(self.dump) if args[0] == "pw-dump" else ""
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")


@pytest.fixture
def fake_run(monkeypatch):
    run = FakeRun()
    monkeypatch.setattr(pipewire.subprocess, "run", run)
    return run


def test_start_links_source_to_default_sink(fake_run):
    router = PipeWireRouter()
    router.start()

    assert router._source_id == 42
    assert [
        c for c in fake_run.calls if c[0] == "pw-link" and "-d" not in c
    ] == [
        [
            "pw-link",
            "alsa_input.usb-Apple_iPod-00.analog-stereo",
            "alsa_output.pci-0000_00.analog",
        ]
    ]


def test_start_uses_explicit_target(fake_run):
    router = PipeWireRouter()
    router.start(target="my-sink")

    assert fake_run.calls[-1] == [
        "pw-link",
        "alsa_input.usb-Apple_iPod-00.analog-stereo",
        "my-sink",
    ]


def test_set_volume_and_mute(fake_run):
    router = PipeWireRouter()
    router.start()

    router.set_volume(0.5)
    router.set_muted(True)

    assert ["wpctl", "set-volume", "42", "0.500"] in fake_run.calls
    assert ["wpctl", "set-mute", "42", "1"] in fake_run.calls


def test_set_volume_clamped(fake_run):
    router = PipeWireRouter()
    router.start()
    router.set_volume(2.0)

    assert ["wpctl", "set-volume", "42", "1.000"] in fake_run.calls


def test_set_rate_pins_clock(fake_run):
    router = PipeWireRouter()
    router.start()
    router.set_rate(44100)

    assert ["pw-metadata", "-n", "settings", "0", "clock.force-rate", "44100"] in fake_run.calls

    # Setting the same rate again is a no-op
    before = len(fake_run.calls)
    router.set_rate(44100)
    assert len(fake_run.calls) == before


def test_stop_restores_clock(fake_run):
    router = PipeWireRouter()
    router.start()
    router.set_rate(44100)
    router.stop()

    assert ["pw-metadata", "-n", "settings", "0", "clock.force-rate", "0"] in fake_run.calls


def test_stop_without_forced_rate_leaves_clock(fake_run):
    router = PipeWireRouter()
    router.start()
    router.stop()

    assert not any(c[:2] == ["pw-metadata", "-n"] for c in fake_run.calls)


def test_start_without_source_raises(monkeypatch):
    monkeypatch.setattr(pipewire.subprocess, "run", FakeRun(dump=[]))
    router = PipeWireRouter()

    with pytest.raises(AudioError, match="No iPod audio source"):
        router.start(timeout=0.0)


def test_create_router_unknown_backend():
    with pytest.raises(AudioError, match="Unknown audio backend"):
        create_audio_router("bogus")


def test_create_router_pipewire_unavailable(monkeypatch):
    monkeypatch.setattr(pipewire.shutil, "which", lambda tool: None)

    with pytest.raises(AudioError, match="PipeWire command line tools"):
        create_audio_router("pipewire")


def test_create_router_auto_prefers_pipewire(monkeypatch):
    monkeypatch.setattr(pipewire.shutil, "which", lambda tool: f"/usr/bin/{tool}")

    assert isinstance(create_audio_router("auto"), PipeWireRouter)
