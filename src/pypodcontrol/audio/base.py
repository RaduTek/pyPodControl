import logging
from abc import ABC, abstractmethod
from typing import Final

from ..errors import AudioError

logger = logging.getLogger(__name__)

DEFAULT_MATCH: Final = ("ipod", "apple")
"""Substrings (case-insensitive) that identify the iPod's audio source by default"""


class AudioRouter(ABC):
    """
    ### AudioRouter

    Routes the iPod's digital audio (a USB audio capture source) to an output,
    applying a gain driven by the volume the iPod reports.

    The iPod emits digital audio at full scale and expects the accessory to
    apply the volume, so set_volume() must be called with the iPod's volume (see
    the Display Remote lingo). Use as a context manager, or call start()/stop().
    """

    def __init__(self, match: str | tuple[str, ...] = DEFAULT_MATCH) -> None:
        """
        - match: Substring (or substrings) that identify the iPod's audio
          source node by name, case-insensitive
        """

        self.match: tuple[str, ...] = (match,) if isinstance(match, str) else tuple(match)

    def _matches(self, *names: str | None) -> bool:
        """Whether any of the names contains one of the match substrings"""

        for name in names:
            if name and any(m.lower() in name.lower() for m in self.match):
                return True
        return False

    @abstractmethod
    def start(self, target: str | None = None, timeout: float = 10.0) -> None:
        """
        Wait for the iPod's audio source and route it to the output

        - target: Output sink/ports to route to, or None for the default output
        - timeout: How long to wait for the iPod's source to appear, in seconds

        Raises AudioError if the source does not appear or routing fails.
        """

    def set_rate(self, rate: int) -> None:
        """
        Match the output to the iPod's sample rate (Hz)

        The iPod only produces digital audio at the rate it negotiates over the
        Digital Audio lingo (TrackNewAudioAttributes); if the USB audio
        interface is opened at a different rate the iPod stalls. Drive this from
        the lingo's track attributes. The default is a no-op for backends that
        cannot change rate at runtime.
        """

    @abstractmethod
    def set_volume(self, level: float) -> None:
        """Set the output gain, 0.0 (silent) to 1.0 (full scale)"""

    @abstractmethod
    def set_muted(self, muted: bool) -> None:
        """Mute or unmute the output"""

    @abstractmethod
    def stop(self) -> None:
        """Tear down the routing (safe to call if not started)"""

    def __enter__(self) -> "AudioRouter":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()


def create_audio_router(
    backend: str = "auto", match: str | tuple[str, ...] = DEFAULT_MATCH
) -> AudioRouter:
    """
    Create an AudioRouter for the given backend

    - backend: "pipewire", "jack", or "auto" to prefer PipeWire when its command
      line tools are present and fall back to JACK
    - match: Passed to the router, see AudioRouter

    Raises AudioError if the requested backend is unavailable.
    """

    backend = backend.lower()

    if backend in ("auto", "pipewire"):
        from .pipewire import PipeWireRouter

        if PipeWireRouter.is_available():
            return PipeWireRouter(match)
        if backend == "pipewire":
            raise AudioError(
                "PipeWire command line tools (pw-dump, pw-link, wpctl) not found"
            )

    if backend in ("auto", "jack"):
        from .jack import JackRouter

        if JackRouter.is_available():
            return JackRouter(match)
        if backend == "jack":
            raise AudioError(
                "JACK backend requires the JACK-Client package: pip install pyPodControl[audio]"
            )

    if backend not in ("auto", "pipewire", "jack"):
        raise AudioError(f"Unknown audio backend: {backend!r}")

    raise AudioError("No audio backend available (install PipeWire tools or JACK-Client)")
