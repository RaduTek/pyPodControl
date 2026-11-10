import json
import logging
import shutil
import subprocess
import time

from ..errors import AudioError
from .base import DEFAULT_MATCH, AudioRouter

logger = logging.getLogger(__name__)

REQUIRED_TOOLS = ("pw-dump", "pw-link", "wpctl", "pw-metadata")
"""Command line tools the PipeWire backend needs"""


class PipeWireRouter(AudioRouter):
    """
    ### PipeWireRouter

    Routes the iPod's audio with PipeWire's command line tools (pw-dump,
    pw-link, wpctl), no extra Python dependency. The iPod's source node volume
    scales the routed stream, so set_volume() applies the gain there.
    """

    @staticmethod
    def is_available() -> bool:
        """Whether PipeWire's command line tools are present"""

        return all(shutil.which(tool) is not None for tool in REQUIRED_TOOLS)

    def __init__(self, match: str | tuple[str, ...] = DEFAULT_MATCH) -> None:
        super().__init__(match)

        self._source_id: int | None = None
        self._source_name: str | None = None
        self._sink: str | None = None
        self._forced_rate: int | None = None

    # --- command helpers ------------------------------------------------------

    @staticmethod
    def _run(args: list[str], check: bool = True) -> str:
        try:
            result = subprocess.run(args, capture_output=True, text=True)
        except FileNotFoundError as e:
            raise AudioError(f"{args[0]} not found: {e}") from e

        if check and result.returncode != 0:
            raise AudioError(
                f"{' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}"
            )

        return result.stdout

    def _dump(self) -> list[dict]:
        try:
            return json.loads(self._run(["pw-dump"]))
        except json.JSONDecodeError as e:
            raise AudioError(f"Could not parse pw-dump output: {e}") from e

    # --- discovery ------------------------------------------------------------

    def _find_source(self, objects: list[dict]) -> tuple[int, str] | None:
        """Find the iPod's audio source node, returns (id, node name)"""

        for obj in objects:
            if obj.get("type") != "PipeWire:Interface:Node":
                continue

            props = obj.get("info", {}).get("props", {})
            if props.get("media.class") != "Audio/Source":
                continue

            name = props.get("node.name")
            if self._matches(
                name,
                props.get("node.description"),
                props.get("device.name"),
                props.get("api.alsa.card.name"),
            ) or str(props.get("device.vendor.id", "")).lower() in ("0x05ac", "1452"):
                return obj["id"], name or str(obj["id"])

        return None

    def _default_sink(self, objects: list[dict]) -> str | None:
        """Name of the default audio sink from the PipeWire metadata"""

        for obj in objects:
            if obj.get("type") != "PipeWire:Interface:Metadata":
                continue

            for entry in obj.get("metadata", []):
                if entry.get("key") == "default.audio.sink":
                    value = entry.get("value")
                    if isinstance(value, dict):
                        return value.get("name")
                    return value

        return None

    # --- routing --------------------------------------------------------------

    def start(self, target: str | None = None, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        source = None

        while True:
            objects = self._dump()
            source = self._find_source(objects)
            if source is not None:
                break
            if time.monotonic() >= deadline:
                raise AudioError(
                    "No iPod audio source found (is the iPod in its iPod USB "
                    "Interface configuration and playing?)"
                )
            time.sleep(0.5)

        self._source_id, self._source_name = source

        self._sink = target or self._default_sink(objects)
        if not self._sink:
            raise AudioError("No output sink given and no default audio sink found")

        logger.info("Routing iPod audio %s -> %s", self._source_name, self._sink)
        self._run(["pw-link", self._source_name, self._sink])

    def set_rate(self, rate: int) -> None:
        # The iPod streams digital audio only at the rate it negotiated over
        # iAP. PipeWire otherwise opens the USB audio interface at its default
        # graph rate (e.g. 48000), which the iPod's supported-rate list allows
        # but its pipeline does not actually produce, so it stalls. Pinning the
        # graph clock to the negotiated rate makes PipeWire reopen the device
        # at that rate. This is global while routing and restored on stop().
        if rate <= 0 or rate == self._forced_rate:
            return

        logger.info("Pinning the PipeWire clock to the iPod's %d Hz", rate)
        self._run(["pw-metadata", "-n", "settings", "0", "clock.force-rate", str(rate)])
        self._forced_rate = rate

    def set_volume(self, level: float) -> None:
        if self._source_id is None:
            return

        level = max(0.0, min(1.0, level))
        self._run(["wpctl", "set-volume", str(self._source_id), f"{level:.3f}"])

    def set_muted(self, muted: bool) -> None:
        if self._source_id is None:
            return

        self._run(["wpctl", "set-mute", str(self._source_id), "1" if muted else "0"])

    def stop(self) -> None:
        if self._source_name and self._sink:
            # Best effort: the links may already be gone if the iPod unplugged
            self._run(["pw-link", "-d", self._source_name, self._sink], check=False)

        if self._forced_rate is not None:
            # Restore automatic clock rate selection (0 = not forced)
            self._run(
                ["pw-metadata", "-n", "settings", "0", "clock.force-rate", "0"],
                check=False,
            )
            self._forced_rate = None

        self._source_id = None
        self._source_name = None
        self._sink = None
