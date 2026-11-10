import logging
import time

from ..errors import AudioError
from .base import DEFAULT_MATCH, AudioRouter

logger = logging.getLogger(__name__)

try:
    import jack
except ImportError:  # pragma: no cover - depends on optional dependency
    jack = None

try:
    import numpy
except ImportError:  # pragma: no cover - JACK-Client pulls numpy in
    numpy = None


class JackRouter(AudioRouter):
    """
    ### JackRouter

    Routes the iPod's audio with JACK (or pipewire-jack). JACK has no per-port
    volume, so the gain is applied in the process callback. Requires the
    JACK-Client package (`pip install pyPodControl[audio]`) and a running JACK
    server.
    """

    @staticmethod
    def is_available() -> bool:
        """Whether the JACK-Client package is importable"""

        return jack is not None and numpy is not None

    def __init__(
        self, match: str | tuple[str, ...] = DEFAULT_MATCH, name: str = "pyPodControl"
    ) -> None:
        if not self.is_available():
            raise AudioError(
                "JACK backend requires the JACK-Client package: pip install pyPodControl[audio]"
            )

        super().__init__(match)

        self._name = name
        self._client: "jack.Client | None" = None
        self._level = 1.0
        self._muted = False

    def _process(self, frames: int) -> None:
        gain = 0.0 if self._muted else self._level
        assert self._client is not None

        for inport, outport in zip(self._client.inports, self._client.outports):
            outport.get_array()[:] = inport.get_array() * gain

    def start(self, target: str | None = None, timeout: float = 10.0) -> None:
        try:
            client = jack.Client(self._name)
        except jack.JackError as e:
            raise AudioError(f"Could not connect to the JACK server: {e}") from e

        # Wait for the iPod's capture ports to appear
        deadline = time.monotonic() + timeout
        sources: list = []
        while True:
            sources = [
                port
                for port in client.get_ports(is_output=True, is_audio=True)
                if self._matches(port.name)
            ]
            if sources:
                break
            if time.monotonic() >= deadline:
                client.close()
                raise AudioError("No iPod audio source ports found in JACK")
            time.sleep(0.5)

        playback = client.get_ports(
            target or "", is_input=True, is_audio=True, is_physical=target is None
        )
        if not playback:
            client.close()
            raise AudioError(f"No output ports found for target {target!r}")

        client.set_process_callback(self._process)

        for i, source in enumerate(sources):
            client.inports.register(f"in_{i}")
            client.outports.register(f"out_{i}")

        client.activate()

        for source, inport in zip(sources, client.inports):
            client.connect(source, inport)
        for i, outport in enumerate(client.outports):
            client.connect(outport, playback[i % len(playback)])

        self._client = client
        logger.info("Routing iPod audio through JACK (%d channels)", len(sources))

    def set_rate(self, rate: int) -> None:
        # JACK's sample rate is fixed by the server and cannot change at
        # runtime. The iPod streams only at its negotiated rate, so a mismatch
        # stalls it: warn so the server can be started at the right rate.
        if self._client is not None and rate > 0 and rate != self._client.samplerate:
            logger.warning(
                "iPod wants %d Hz but the JACK server runs at %d Hz; restart "
                "JACK at %d Hz or the iPod will not stream",
                rate,
                self._client.samplerate,
                rate,
            )

    def set_volume(self, level: float) -> None:
        self._level = max(0.0, min(1.0, level))

    def set_muted(self, muted: bool) -> None:
        self._muted = muted

    def stop(self) -> None:
        if self._client is not None:
            self._client.deactivate()
            self._client.close()
            self._client = None
