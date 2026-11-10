import logging
from dataclasses import dataclass
from typing import Callable, Final, Iterable

from ..packet import Packet, encode_int
from .lingo import Lingo

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_RATE_CAPS: Final = (8000, 11025, 16000, 22050, 24000, 32000, 44100, 48000)
"""Sample rates (Hz) advertised to the iPod by default"""


@dataclass(frozen=True)
class TrackAttributes:
    """Audio attributes of a track, reported by TrackNewAudioAttributes"""

    sample_rate: int
    """Sample rate in Hz"""

    sound_check: bytes = b""
    """Remaining sound check / gain bytes, as sent by the iPod"""


AudioAttributesListener = Callable[[TrackAttributes], None]
"""Callback invoked with a new track's audio attributes"""


class DigitalAudio(Lingo):
    """
    ### Digital Audio Lingo (0x0A)

    Digital audio output from the iPod over USB (sample rates, track audio
    attributes, video delay)

    This is an accessory-side lingo: the iPod asks for the accessory's sample
    rate capabilities and notifies the sample rate of each new track. Register
    it so the iPod routes its audio to the USB audio interface; the actual PCM
    is carried by the USB audio class device, not by iAP (see
    `pypodcontrol.audio`).
    """

    LINGO_ID: Final = 0x0A

    COMMANDS = {
        "AccessoryAck": 0x00,
        "iPodAck": 0x01,
        "GetAccessorySampleRateCaps": 0x02,
        "RetAccessorySampleRateCaps": 0x03,
        "TrackNewAudioAttributes": 0x04,
        "SetVideoDelay": 0x05,
    }
    """Available commands"""

    ACK_COMMAND = "iPodAck"

    def __init__(self, sample_rate_caps: Iterable[int] | None = None) -> None:
        """
        Create the lingo

        - sample_rate_caps: Sample rates (Hz) to advertise to the iPod,
          defaulting to DEFAULT_SAMPLE_RATE_CAPS
        """

        super().__init__()

        self.sample_rate_caps: tuple[int, ...] = tuple(
            sample_rate_caps if sample_rate_caps is not None else DEFAULT_SAMPLE_RATE_CAPS
        )
        self.sample_rate: int | None = None
        """Sample rate of the current track in Hz, None until the first notification"""

        self._attributes_listeners: list[AudioAttributesListener] = []

    # --- track audio attributes -----------------------------------------------

    def add_track_attributes_listener(self, listener: AudioAttributesListener) -> None:
        """
        Call listener(attributes) when the iPod notifies a new track's audio
        attributes (TrackNewAudioAttributes)

        Listeners run on the client's event thread and may send requests.
        """

        self._attributes_listeners.append(listener)

    def remove_track_attributes_listener(
        self, listener: AudioAttributesListener
    ) -> None:
        """Remove a listener added with add_track_attributes_listener()"""

        if listener in self._attributes_listeners:
            self._attributes_listeners.remove(listener)

    # --- accessory-side handling ----------------------------------------------

    def handle_packet(self, packet: Packet) -> None:
        command_id = packet.command_id

        if command_id == self.command_id("GetAccessorySampleRateCaps"):
            self._on_get_sample_rate_caps()
        elif command_id == self.command_id("TrackNewAudioAttributes"):
            self._on_track_new_audio_attributes(packet)
        elif command_id == self.command_id("SetVideoDelay"):
            self._ack(command_id)
        else:
            super().handle_packet(packet)
            return

        self.notify_listeners(packet)

    def _on_get_sample_rate_caps(self) -> None:
        """The iPod asks which sample rates the accessory supports"""

        caps = b"".join(encode_int(rate) for rate in self.sample_rate_caps)
        self.send("RetAccessorySampleRateCaps", caps)

    def _on_track_new_audio_attributes(self, packet: Packet) -> None:
        """The iPod notifies the new track's sample rate"""

        if len(packet.data) < 4:
            logger.debug("Malformed TrackNewAudioAttributes: %s", packet.data.hex(" "))
            self._ack(packet.command_id)
            return

        attributes = TrackAttributes(
            int.from_bytes(packet.data[:4], "big"), packet.data[4:]
        )
        self.sample_rate = attributes.sample_rate

        listeners = list(self._attributes_listeners)

        def run() -> None:
            for listener in listeners:
                try:
                    listener(attributes)
                except Exception:
                    logger.exception("DigitalAudio: track attributes listener failed")

        if listeners:
            self.iap.dispatch(run)

        self._ack(packet.command_id)

    def _ack(self, command_id: int, status: int = Lingo.ACK_SUCCESS) -> None:
        """Acknowledge an iPod command with an AccessoryAck"""

        self.send("AccessoryAck", bytes([status, command_id]))

    def close(self) -> None:
        """
        Reset the negotiated sample rate and drop the attributes listeners

        The sample rate belongs to the closed connection, and releasing the
        listeners lets anything they capture (such as an audio router) be
        collected once the client is done.
        """

        self.sample_rate = None
        self._attributes_listeners.clear()
