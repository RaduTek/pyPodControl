from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Any, Callable, Final, Iterable

from ..packet import Packet, encode_byte, encode_int, encode_short
from .lingo import Lingo


class RemoteEvent(IntEnum):
    """Apple device events of SetRemoteEventNotification / RemoteEventNotification"""

    TRACK_POSITION_MS = 0x00
    TRACK_INDEX = 0x01
    CHAPTER = 0x02
    PLAY_STATE = 0x03
    VOLUME = 0x04
    """Mute state and UI volume"""
    POWER_BATTERY = 0x05
    EQUALIZER = 0x06
    SHUFFLE = 0x07
    REPEAT = 0x08
    DATE_TIME = 0x09
    ALARM = 0x0A
    """Deprecated"""
    BACKLIGHT = 0x0B
    HOLD_SWITCH = 0x0C
    SOUND_CHECK = 0x0D
    AUDIOBOOK_SPEED = 0x0E
    TRACK_POSITION_S = 0x0F
    ABSOLUTE_VOLUME = 0x10
    """Mute state, UI volume and absolute volume"""
    TRACK_CAPABILITIES = 0x11
    PLAYBACK_ENGINE_CONTENTS = 0x12
    """Number of tracks in the new playlist"""


class PlayState(IntEnum):
    """Playback engine state"""

    STOPPED = 0x00
    PLAYING = 0x01
    PAUSED = 0x02
    FAST_FORWARD = 0x03
    REWIND = 0x04
    END_FAST_FORWARD_REWIND = 0x05


class TrackInfoType(IntEnum):
    """Info types of GetIndexedPlayingTrackInfo"""

    CAPS = 0x00
    CHAPTER = 0x01
    ARTIST = 0x02
    ALBUM = 0x03
    GENRE = 0x04
    TITLE = 0x05
    COMPOSER = 0x06
    LYRICS = 0x07
    ARTWORK_COUNT = 0x08


@dataclass(frozen=True)
class Volume:
    """Mute state and volume levels (0-255), levels are 0 while muted"""

    muted: bool
    ui_level: int
    absolute_level: int | None = None
    """Only reported by the ABSOLUTE_VOLUME event"""


@dataclass(frozen=True)
class PlayStatus:
    """Play status, the track fields are only valid while playing or paused"""

    state: PlayState
    track_index: int
    track_length_ms: int
    track_position_ms: int


EventListener = Callable[[RemoteEvent, Any], None]
"""Callback invoked with a remote event and its decoded value"""


class DisplayRemote(Lingo):
    """
    ### Display Remote Lingo (0x03)

    Remote control of the iPod with a display (EQ, state info, play status, track info, artwork)
    """

    LINGO_ID: Final = 0x03

    COMMANDS = {
        "iPodAck": 0x00,
        "GetCurrentEQProfileIndex": 0x01,
        "RetCurrentEQProfileIndex": 0x02,
        "SetCurrentEQProfileIndex": 0x03,
        "GetNumEQProfiles": 0x04,
        "RetNumEQProfiles": 0x05,
        "GetIndexedEQProfileName": 0x06,
        "RetIndexedEQProfileName": 0x07,
        "SetRemoteEventNotification": 0x08,
        "RemoteEventNotification": 0x09,
        "GetRemoteEventStatus": 0x0A,
        "RetRemoteEventStatus": 0x0B,
        "GetiPodStateInfo": 0x0C,
        "RetiPodStateInfo": 0x0D,
        "SetiPodStateInfo": 0x0E,
        "GetPlayStatus": 0x0F,
        "RetPlayStatus": 0x10,
        "SetCurrentPlayingTrack": 0x11,
        "GetIndexedPlayingTrackInfo": 0x12,
        "RetIndexedPlayingTrackInfo": 0x13,
        "GetNumPlayingTracks": 0x14,
        "RetNumPlayingTracks": 0x15,
        "GetArtworkFormats": 0x16,
        "RetArtworkFormats": 0x17,
        "GetTrackArtworkData": 0x18,
        "RetTrackArtworkData": 0x19,
        "GetPowerBatteryState": 0x1A,
        "RetPowerBatteryState": 0x1B,
        "GetSoundCheckState": 0x1C,
        "RetSoundCheckState": 0x1D,
        "SetSoundCheckState": 0x1E,
        "GetTrackArtworkTimes": 0x1F,
        "RetTrackArtworkTimes": 0x20,
        "CreateGeniusPlaylist": 0x21,
        "IsGeniusAvailableForTrack": 0x22,
    }
    """Available commands"""

    ACK_COMMAND = "iPodAck"

    def __init__(self) -> None:
        super().__init__()

        self._event_listeners: dict[RemoteEvent | None, list[EventListener]] = {}
        self.add_listener("RemoteEventNotification", self._on_remote_event)

    # --- remote events --------------------------------------------------------
    #
    # The iPod sends RemoteEventNotification for the events enabled with
    # SetRemoteEventNotification, at most every 500 ms (100 ms for volume).
    # Notifications are reset when the accessory detaches.

    def set_remote_event_notification(self, events: Iterable[RemoteEvent]) -> None:
        """Enable notifications for the given events, disabling all others"""

        mask = 0
        for event in events:
            mask |= 1 << RemoteEvent(event)

        self.request("SetRemoteEventNotification", encode_int(mask))

    def add_event_listener(
        self, event: RemoteEvent | None, listener: EventListener
    ) -> None:
        """
        Call listener(event, value) when the iPod notifies the given event,
        or every event if None

        The value is decoded per event, see decode_remote_event(). Listeners
        run on the client's event thread and may send requests to the iPod.
        Enable the events with set_remote_event_notification().
        """

        self._event_listeners.setdefault(event, []).append(listener)

    def remove_event_listener(
        self, event: RemoteEvent | None, listener: EventListener
    ) -> None:
        """Remove a listener added with add_event_listener()"""

        listeners = self._event_listeners.get(event, [])
        if listener in listeners:
            listeners.remove(listener)

    def _on_remote_event(self, packet: Packet) -> None:
        if not packet.data:
            return

        try:
            event = RemoteEvent(packet.data[0])
        except ValueError:
            return

        value = self.decode_remote_event(event, packet.data[1:])

        listeners = self._event_listeners.get(event, []) + self._event_listeners.get(None, [])
        for listener in listeners:
            listener(event, value)

    @staticmethod
    def decode_remote_event(event: RemoteEvent, data: bytes) -> Any:
        """
        Decode the data of a remote event

        - TRACK_POSITION_MS, TRACK_POSITION_S: position (int)
        - TRACK_INDEX, EQUALIZER, PLAYBACK_ENGINE_CONTENTS: index or count (int)
        - TRACK_CAPABILITIES: capability bits (int)
        - CHAPTER: (track index, chapter count, chapter index)
        - PLAY_STATE: PlayState
        - VOLUME, ABSOLUTE_VOLUME: Volume
        - POWER_BATTERY: (power state, battery level 0-255)
        - SHUFFLE, REPEAT, BACKLIGHT: state or level (int)
        - HOLD_SWITCH, SOUND_CHECK: bool
        - AUDIOBOOK_SPEED: -1 (slower), 0 (normal) or 1 (faster)
        - DATE_TIME: datetime
        - others: the raw data (bytes)
        """

        def number(size: int, signed: bool = False) -> int:
            return int.from_bytes(data[:size], "big", signed=signed)

        if event in (
            RemoteEvent.TRACK_POSITION_MS,
            RemoteEvent.TRACK_INDEX,
            RemoteEvent.EQUALIZER,
            RemoteEvent.TRACK_CAPABILITIES,
            RemoteEvent.PLAYBACK_ENGINE_CONTENTS,
        ):
            return number(4)
        if event == RemoteEvent.TRACK_POSITION_S:
            return number(2)
        if event == RemoteEvent.CHAPTER:
            return (
                int.from_bytes(data[0:4], "big"),
                int.from_bytes(data[4:6], "big"),
                int.from_bytes(data[6:8], "big"),
            )
        if event == RemoteEvent.PLAY_STATE:
            try:
                return PlayState(data[0])
            except ValueError:
                return data[0]
        if event == RemoteEvent.VOLUME:
            return Volume(bool(data[0]), data[1])
        if event == RemoteEvent.ABSOLUTE_VOLUME:
            return Volume(bool(data[0]), data[1], data[2])
        if event == RemoteEvent.POWER_BATTERY:
            return data[0], data[1]
        if event in (RemoteEvent.SHUFFLE, RemoteEvent.REPEAT, RemoteEvent.BACKLIGHT):
            return data[0]
        if event in (RemoteEvent.HOLD_SWITCH, RemoteEvent.SOUND_CHECK):
            return bool(data[0])
        if event == RemoteEvent.AUDIOBOOK_SPEED:
            return number(1, signed=True)
        if event == RemoteEvent.DATE_TIME:
            return datetime(int.from_bytes(data[0:2], "big"), data[2], data[3], data[4], data[5])

        return data

    # --- playback -------------------------------------------------------------

    def get_play_status(self) -> PlayStatus:
        """Get the play state and the current track's index, length and position"""

        response = self.request("GetPlayStatus", response="RetPlayStatus")
        data = response.data

        if len(data) < 13:
            raise ValueError(f"Malformed play status response: {data.hex(' ')}")

        return PlayStatus(
            PlayState(data[0]),
            int.from_bytes(data[1:5], "big"),
            int.from_bytes(data[5:9], "big"),
            int.from_bytes(data[9:13], "big"),
        )

    def get_num_playing_tracks(self) -> int:
        """Get the number of tracks in the playing list"""

        response = self.request("GetNumPlayingTracks", response="RetNumPlayingTracks")
        return int.from_bytes(response.data[:4], "big")

    def get_indexed_playing_track_info(
        self, info_type: TrackInfoType, track_index: int, chapter_index: int = 0
    ) -> bytes:
        """Get a type of information about a playing track, returns the raw info data"""

        response = self.request(
            "GetIndexedPlayingTrackInfo",
            encode_byte(info_type) + encode_int(track_index) + encode_short(chapter_index),
            response="RetIndexedPlayingTrackInfo",
        )

        return response.data[1:]

    def get_track_text(self, info_type: TrackInfoType, track_index: int) -> str:
        """Get a string about a playing track: ARTIST, ALBUM, GENRE, TITLE or COMPOSER"""

        data = self.get_indexed_playing_track_info(info_type, track_index)
        return data.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
