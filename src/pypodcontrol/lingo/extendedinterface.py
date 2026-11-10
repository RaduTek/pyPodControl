import logging
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, IntFlag
from typing import TYPE_CHECKING, Any, Callable, Final, Iterable

from ..errors import iAPAckError
from ..image import PixelFormat, decode_image, encode_image
from ..image import row_size as image_row_size
from ..packet import Packet, encode_byte, encode_int, encode_long, encode_short
from .lingo import Lingo

if TYPE_CHECKING:
    from PIL.Image import Image

logger = logging.getLogger(__name__)


class DBCategory(IntEnum):
    """Database category types"""

    TOP_LEVEL = 0x00
    PLAYLIST = 0x01
    ARTIST = 0x02
    ALBUM = 0x03
    GENRE = 0x04
    TRACK = 0x05
    COMPOSER = 0x06
    AUDIOBOOK = 0x07
    PODCAST = 0x08
    NESTED_PLAYLIST = 0x09
    GENIUS_MIXES = 0x0A
    ITUNES_U = 0x0B


class DBHierarchy(IntEnum):
    """Database hierarchies of ResetDBSelectionHierarchy"""

    AUDIO = 0x01
    VIDEO = 0x02


class SortOrder(IntEnum):
    """Database sort orders of the deprecated SelectSortDBRecord"""

    GENRE = 0x00
    ARTIST = 0x01
    COMPOSER = 0x02
    ALBUM = 0x03
    NAME = 0x04
    RELEASE_DATE = 0x06
    SERIES = 0x07
    SEASON = 0x08
    EPISODE = 0x09
    DEFAULT = 0xFF


class PlayerState(IntEnum):
    """Player state of ReturnPlayStatus"""

    STOPPED = 0x00
    PLAYING = 0x01
    PAUSED = 0x02
    ERROR = 0xFF


class PlayControlCommand(IntEnum):
    """Play control command codes of PlayControl"""

    TOGGLE_PLAY_PAUSE = 0x01
    STOP = 0x02
    NEXT_TRACK = 0x03
    """Deprecated, use NEXT"""
    PREVIOUS_TRACK = 0x04
    """Deprecated, use PREVIOUS"""
    START_FF = 0x05
    """Must be followed by END_FF_REW before other play control commands"""
    START_REW = 0x06
    """Must be followed by END_FF_REW before other play control commands"""
    END_FF_REW = 0x07
    NEXT = 0x08
    """Next chapter, or next track if it has no more chapters"""
    PREVIOUS = 0x09
    """Start of the chapter (track), or previous one within its first 2 seconds"""
    PLAY = 0x0A
    PAUSE = 0x0B
    NEXT_CHAPTER = 0x0C
    """Deprecated, use NEXT"""
    PREVIOUS_CHAPTER = 0x0D
    """Deprecated, use PREVIOUS"""
    RESUME_IPOD = 0x0E
    """Resume playback in the built-in Music app (restricted use)"""


class ShuffleMode(IntEnum):
    OFF = 0x00
    TRACKS = 0x01
    ALBUMS = 0x02


class RepeatMode(IntEnum):
    OFF = 0x00
    ONE = 0x01
    ALL = 0x02


class AudiobookSpeed(IntEnum):
    SLOWER = -1
    NORMAL = 0
    FASTER = 1


class PlayingTrackInfoType(IntEnum):
    """Info types of GetIndexedPlayingTrackInfo"""

    CAPS = 0x00
    """TrackCapsInfo"""
    PODCAST_NAME = 0x01
    RELEASE_DATE = 0x02
    """datetime, or None if the track has no release date"""
    DESCRIPTION = 0x03
    LYRICS = 0x04
    GENRE = 0x05
    COMPOSER = 0x06
    ARTWORK_COUNT = 0x07
    """{format ID: image count}"""


class TrackCapability(IntFlag):
    """Track capability bits"""

    AUDIOBOOK = 1 << 0
    HAS_CHAPTERS = 1 << 1
    HAS_ARTWORK = 1 << 2
    HAS_LYRICS = 1 << 3
    PODCAST_EPISODE = 1 << 4
    HAS_RELEASE_DATE = 1 << 5
    HAS_DESCRIPTION = 1 << 6
    VIDEO = 1 << 7
    QUEUED_AS_VIDEO = 1 << 8
    GENIUS_CAPABLE = 1 << 13
    ITUNES_U_EPISODE = 1 << 14


class TrackInfoBit(IntEnum):
    """
    Track information types of GetUIDTrackInfo, GetDBTrackInfo and
    GetPBTrackInfo (bit positions of the request mask)
    """

    CAPABILITIES = 0
    """TrackCapability"""
    NAME = 1
    ARTIST = 2
    ALBUM = 3
    GENRE = 4
    COMPOSER = 5
    DURATION = 6
    """Milliseconds"""
    UID = 7
    CHAPTER_COUNT = 8
    CHAPTER_TIMES = 9
    """[(chapter index, offset in ms)]"""
    CHAPTER_NAMES = 10
    """[(chapter index, name)]"""
    LYRICS = 11
    """Only for the track playing in the Playback Engine"""
    DESCRIPTION = 12
    ALBUM_TRACK_INDEX = 13
    DISC_SET_ALBUM_INDEX = 14
    PLAY_COUNT = 15
    SKIP_COUNT = 16
    PODCAST_RELEASE_DATE = 17
    """datetime or None"""
    LAST_PLAYED = 18
    """datetime, or None if never played"""
    YEAR = 19
    STAR_RATING = 20
    """0 to 100, 20 per star"""
    SERIES_NAME = 21
    SEASON_NUMBER = 22
    VOLUME_ADJUST = 23
    """-100 to 100 (%)"""
    EQ_PRESET = 24
    DATA_RATE = 25
    """Kilobits per second"""
    BOOKMARK_OFFSET = 26
    """Milliseconds"""
    START_STOP_OFFSET = 27
    """(start ms, stop ms)"""


class iTunesInfoType(IntEnum):
    """iTunes database metadata types of GetDBiTunesInfo"""

    DATABASE_UID = 0x00
    LAST_SYNC = 0x01
    """datetime"""
    AUDIO_TRACK_COUNT = 0x02
    VIDEO_TRACK_COUNT = 0x03
    AUDIOBOOK_COUNT = 0x04
    PHOTO_COUNT = 0x05


class TrackIdentifierType(IntEnum):
    """How a track is identified by GetArtworkTimes and GetArtworkData"""

    UID = 0x00
    PLAYBACK_INDEX = 0x01
    DATABASE_INDEX = 0x02


class IndexType(IntEnum):
    """Engine a track index of the Genius commands refers to"""

    DATABASE = 0x00
    PLAYBACK = 0x01


class PlayStatusEvent(IntEnum):
    """Events of SetPlayStatusChangeNotification (bit positions of the mask)"""

    BASIC_PLAY_STATE = 0
    """PLAYBACK_STOPPED, FFW_SEEK_STOP and REW_SEEK_STOP changes"""
    EXTENDED_PLAY_STATE = 1
    """PLAYBACK_STATUS_EXTENDED changes"""
    TRACK_INDEX = 2
    TRACK_TIME_MS = 3
    TRACK_TIME_S = 4
    CHAPTER_INDEX = 5
    CHAPTER_TIME_MS = 6
    CHAPTER_TIME_S = 7
    TRACK_UID = 8
    TRACK_MEDIA_TYPE = 9
    TRACK_LYRICS_READY = 10
    TRACK_CAPABILITIES = 11
    PLAYBACK_ENGINE_CONTENTS = 12


class PlayStatusChange(IntEnum):
    """Status change codes of PlayStatusChangeNotification"""

    PLAYBACK_STOPPED = 0x00
    TRACK_INDEX = 0x01
    FFW_SEEK_STOP = 0x02
    REW_SEEK_STOP = 0x03
    TRACK_TIME_MS = 0x04
    CHAPTER_INDEX = 0x05
    PLAYBACK_STATUS_EXTENDED = 0x06
    TRACK_TIME_S = 0x07
    CHAPTER_TIME_MS = 0x08
    CHAPTER_TIME_S = 0x09
    TRACK_UID = 0x0A
    TRACK_PLAYBACK_MODE = 0x0B
    TRACK_LYRICS_READY = 0x0C
    TRACK_CAPABILITIES = 0x0D
    PLAYBACK_ENGINE_CONTENTS = 0x0E


class ExtendedPlayState(IntEnum):
    """Play states of the PLAYBACK_STATUS_EXTENDED notification"""

    STOPPED = 0x02
    FFW_SEEK_STARTED = 0x05
    REW_SEEK_STARTED = 0x06
    SEEK_STOPPED = 0x07
    PLAYING = 0x0A
    PAUSED = 0x0B


class PlaybackMode(IntEnum):
    """Playback mode of the TRACK_PLAYBACK_MODE notification"""

    AUDIO = 0x00
    VIDEO = 0x01


@dataclass(frozen=True)
class ChapterInfo:
    """Chapter of the playing track, index is -1 and count 0 without chapters"""

    index: int
    count: int


@dataclass(frozen=True)
class ChapterPlayStatus:
    length_ms: int
    elapsed_ms: int


@dataclass(frozen=True)
class PlayerStatus:
    """Play status, length and position are only valid while playing or paused"""

    length_ms: int
    position_ms: int
    state: PlayerState


@dataclass(frozen=True)
class TrackCapsInfo:
    """Track capabilities and information of GetIndexedPlayingTrackInfo"""

    capabilities: TrackCapability
    length_ms: int
    chapter_count: int


@dataclass(frozen=True)
class ArtworkFormat:
    """Artwork format supported by the iPod"""

    format_id: int
    pixel_format: int
    width: int
    height: int


@dataclass(frozen=True)
class DisplayImageLimits:
    """Largest display image accepted by SetDisplayImage in a pixel format"""

    width: int
    height: int
    pixel_format: int


@dataclass(frozen=True)
class Artwork:
    """Artwork image received from the iPod"""

    pixel_format: int
    width: int
    height: int
    inset: tuple[int, int, int, int]
    """Inset rectangle without padding: top-left x, y, bottom-right x, y"""
    row_size: int
    """Bytes per row of pixel data"""
    data: bytes
    """Raw pixel data"""

    def to_image(self, crop_inset: bool = False) -> "Image":
        """
        Convert to a Pillow image ("RGB", or "L" for monochrome), needs Pillow

        - crop_inset: Crop to the inset rectangle, removing the padding the
          iPod may have added
        """

        image = decode_image(
            self.pixel_format, self.width, self.height, self.row_size, self.data
        )

        if crop_inset:
            x1, y1, x2, y2 = self.inset
            # The bottom-right point is the last pixel inside the rectangle
            box = (x1, y1, min(x2 + 1, self.width), min(y2 + 1, self.height))
            if box[0] < box[2] and box[1] < box[3]:
                image = image.crop(box)

        return image


EventListener = Callable[[PlayStatusChange, Any], None]
"""Callback invoked with a play status change and its decoded value"""


def _string(data: bytes) -> str:
    """Decode a null-terminated UTF-8 string"""

    return data.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


def _number(data: bytes, signed: bool = False) -> int:
    return int.from_bytes(data, "big", signed=signed)


def _datetime(data: bytes) -> datetime | None:
    """Decode a date/time (seconds, minutes, hours, day, month, year:2), None if unset"""

    if len(data) < 7 or not any(data[:7]):
        return None

    try:
        return datetime(_number(data[5:7]), data[4], data[3], data[2], data[1], data[0])
    except ValueError:
        return None


def _check_length(data: bytes, length: int, what: str) -> None:
    if len(data) < length:
        raise ValueError(f"Malformed {what} response: {data.hex(' ')}")


class ExtendedInterface(Lingo):
    """
    ### Extended Interface Lingo (0x04)

    Advanced control of the iPod (database browsing, playback, track info)

    The iPod must be in Extended Interface mode, see enter_extended_mode().
    """

    LINGO_ID: Final = 0x04

    COMMANDS = {
        "ACK": 0x0001,
        "GetCurrentPlayingTrackChapterInfo": 0x0002,
        "ReturnCurrentPlayingTrackChapterInfo": 0x0003,
        "SetCurrentPlayingTrackChapter": 0x0004,
        "GetCurrentPlayingTrackChapterPlayStatus": 0x0005,
        "ReturnCurrentPlayingTrackChapterPlayStatus": 0x0006,
        "GetCurrentPlayingTrackChapterName": 0x0007,
        "ReturnCurrentPlayingTrackChapterName": 0x0008,
        "GetAudiobookSpeed": 0x0009,
        "ReturnAudiobookSpeed": 0x000A,
        "SetAudiobookSpeed": 0x000B,
        "GetIndexedPlayingTrackInfo": 0x000C,
        "ReturnIndexedPlayingTrackInfo": 0x000D,
        "GetArtworkFormats": 0x000E,
        "RetArtworkFormats": 0x000F,
        "GetTrackArtworkData": 0x0010,
        "RetTrackArtworkData": 0x0011,
        "RequestProtocolVersion": 0x0012,
        "ReturnProtocolVersion": 0x0013,
        "RequestiPodName": 0x0014,
        "ReturniPodName": 0x0015,
        "ResetDBSelection": 0x0016,
        "SelectDBRecord": 0x0017,
        "GetNumberCategorizedDBRecords": 0x0018,
        "ReturnNumberCategorizedDBRecords": 0x0019,
        "RetrieveCategorizedDatabaseRecords": 0x001A,
        "ReturnCategorizedDatabaseRecord": 0x001B,
        "GetPlayStatus": 0x001C,
        "ReturnPlayStatus": 0x001D,
        "GetCurrentPlayingTrackIndex": 0x001E,
        "ReturnCurrentPlayingTrackIndex": 0x001F,
        "GetIndexedPlayingTrackTitle": 0x0020,
        "ReturnIndexedPlayingTrackTitle": 0x0021,
        "GetIndexedPlayingTrackArtistName": 0x0022,
        "ReturnIndexedPlayingTrackArtistName": 0x0023,
        "GetIndexedPlayingTrackAlbumName": 0x0024,
        "ReturnIndexedPlayingTrackAlbumName": 0x0025,
        "SetPlayStatusChangeNotification": 0x0026,
        "PlayStatusChangeNotification": 0x0027,
        "PlayCurrentSelection": 0x0028,
        "PlayControl": 0x0029,
        "GetTrackArtworkTimes": 0x002A,
        "RetTrackArtworkTimes": 0x002B,
        "GetShuffle": 0x002C,
        "ReturnShuffle": 0x002D,
        "SetShuffle": 0x002E,
        "GetRepeat": 0x002F,
        "ReturnRepeat": 0x0030,
        "SetRepeat": 0x0031,
        "SetDisplayImage": 0x0032,
        "GetMonoDisplayImageLimits": 0x0033,
        "ReturnMonoDisplayImageLimits": 0x0034,
        "GetNumPlayingTracks": 0x0035,
        "ReturnNumPlayingTracks": 0x0036,
        "SetCurrentPlayingTrack": 0x0037,
        "SelectSortDBRecord": 0x0038,
        "GetColorDisplayImageLimits": 0x0039,
        "ReturnColorDisplayImageLimits": 0x003A,
        "ResetDBSelectionHierarchy": 0x003B,
        "GetDBiTunesInfo": 0x003C,
        "RetDBiTunesInfo": 0x003D,
        "GetUIDTrackInfo": 0x003E,
        "RetUIDTrackInfo": 0x003F,
        "GetDBTrackInfo": 0x0040,
        "RetDBTrackInfo": 0x0041,
        "GetPBTrackInfo": 0x0042,
        "RetPBTrackInfo": 0x0043,
        "CreateGeniusPlaylist": 0x0044,
        "RefreshGeniusPlaylist": 0x0045,
        "IsGeniusAvailableForTrack": 0x0047,
        "GetPlaylistInfo": 0x0048,
        "RetPlaylistInfo": 0x0049,
        "PrepareUIDList": 0x004A,
        "PlayPreparedUIDList": 0x004B,
        "GetArtworkTimes": 0x004C,
        "RetArtworkTimes": 0x004D,
        "GetArtworkData": 0x004E,
        "RetArtworkData": 0x004F,
    }
    """Available commands"""

    EXTENDED_COMMAND_IDS = True

    ACK_COMMAND = "ACK"

    ACK_BAD_PARAMETER: Final = 0x04
    """ACK status: bad parameter"""

    ACK_NOT_GENIUS: Final = 0x12
    """ACK status: no Genius information, or not a Genius playlist"""

    ACK_SECTION_RECEIVED: Final = 0x13
    """ACK status: multisection data section received, send the next one"""

    UI_MODE_STANDARD: Final = 0x00
    UI_MODE_EXTENDED: Final = 0x01
    """General lingo SetUIMode modes"""

    MULTI_PACKET_BITS: Final = frozenset(
        {TrackInfoBit.CHAPTER_TIMES, TrackInfoBit.CHAPTER_NAMES, TrackInfoBit.LYRICS}
    )
    """Track information types the iPod may split into several packets"""

    def __init__(self) -> None:
        super().__init__()

        self._max_payload: int | None = None
        self._event_listeners: dict[PlayStatusChange | None, list[EventListener]] = {}
        self.add_listener("PlayStatusChangeNotification", self._on_play_status_change)

    # --- mode -----------------------------------------------------------------
    #
    # Extended Interface commands only work in Extended Interface mode. The
    # iPod leaves it when the accessory exits it, identifies again with IDPS
    # or is disconnected.

    def enter_extended_mode(self) -> None:
        """
        Put the iPod in Extended Interface mode, the lingo must have been
        identified (pausing audio and stopping video playback)
        """

        general = self.iap.general

        try:
            general.request("SetUIMode", encode_byte(self.UI_MODE_EXTENDED))
        except iAPAckError as e:
            # Older iPods only support the deprecated command
            if e.status != self.ACK_BAD_PARAMETER:
                raise
            general.request("EnterRemoteUIMode")

    def exit_extended_mode(self) -> None:
        """Return the iPod to its standard user interface"""

        general = self.iap.general

        try:
            general.request("SetUIMode", encode_byte(self.UI_MODE_STANDARD))
        except iAPAckError as e:
            if e.status != self.ACK_BAD_PARAMETER:
                raise
            general.request("ExitRemoteUIMode")

    def is_extended_mode(self) -> bool:
        """Whether the iPod is in Extended Interface mode"""

        general = self.iap.general

        try:
            response = general.request("GetUIMode", response="RetUIMode")
        except iAPAckError as e:
            if e.status != self.ACK_BAD_PARAMETER:
                raise
            response = general.request("RequestRemoteUIMode", response="ReturnRemoteUIMode")
            return bool(response.data[:1] != b"\x00")

        return response.data[:1] == encode_byte(self.UI_MODE_EXTENDED)

    # --- play status notifications --------------------------------------------

    def set_play_status_change_notification(
        self, events: Iterable[PlayStatusEvent] | bool
    ) -> bool:
        """
        Enable notifications for the given events, disabling all others

        Pass True or False to enable or disable the basic set of notifications
        (play state, track index, track time, seek stop and chapter index).
        iPods that refuse the event mask fall back to the basic set, returns
        whether the mask was accepted.
        """

        if isinstance(events, bool):
            self.request("SetPlayStatusChangeNotification", encode_byte(int(events)))
            return False

        mask = 0
        for event in events:
            mask |= 1 << PlayStatusEvent(event)

        try:
            self.request("SetPlayStatusChangeNotification", encode_int(mask))
            return True
        except iAPAckError as e:
            logger.info("Play status event mask refused (%s), using the basic set", e)

        self.request("SetPlayStatusChangeNotification", encode_byte(int(mask != 0)))
        return False

    def add_event_listener(
        self, change: PlayStatusChange | None, listener: EventListener
    ) -> None:
        """
        Call listener(change, value) when the iPod notifies the given play
        status change, or every change if None

        The value is decoded per change, see decode_play_status_change().
        Listeners run on the client's event thread and may send requests to
        the iPod. Enable the notifications with set_play_status_change_notification().
        """

        self._event_listeners.setdefault(change, []).append(listener)

    def remove_event_listener(
        self, change: PlayStatusChange | None, listener: EventListener
    ) -> None:
        """Remove a listener added with add_event_listener()"""

        listeners = self._event_listeners.get(change, [])
        if listener in listeners:
            listeners.remove(listener)

    def _on_play_status_change(self, packet: Packet) -> None:
        if not packet.data:
            return

        try:
            change = PlayStatusChange(packet.data[0])
        except ValueError:
            return

        value = self.decode_play_status_change(change, packet.data[1:])

        listeners = self._event_listeners.get(change, []) + self._event_listeners.get(None, [])
        for listener in listeners:
            listener(change, value)

    @staticmethod
    def decode_play_status_change(change: PlayStatusChange, data: bytes) -> Any:
        """
        Decode the data of a play status change

        - PLAYBACK_STOPPED, FFW_SEEK_STOP, REW_SEEK_STOP, TRACK_LYRICS_READY: None
        - TRACK_INDEX, CHAPTER_INDEX: index (int, -1 if none)
        - TRACK_TIME_MS, TRACK_TIME_S, CHAPTER_TIME_MS, CHAPTER_TIME_S: time (int)
        - PLAYBACK_ENGINE_CONTENTS: number of tracks (int)
        - TRACK_UID: UID (int)
        - PLAYBACK_STATUS_EXTENDED: ExtendedPlayState
        - TRACK_PLAYBACK_MODE: PlaybackMode
        - TRACK_CAPABILITIES: TrackCapability
        - others: the raw data (bytes)
        """

        if change in (
            PlayStatusChange.PLAYBACK_STOPPED,
            PlayStatusChange.FFW_SEEK_STOP,
            PlayStatusChange.REW_SEEK_STOP,
            PlayStatusChange.TRACK_LYRICS_READY,
        ):
            return None
        if change in (PlayStatusChange.TRACK_INDEX, PlayStatusChange.CHAPTER_INDEX):
            return _number(data[:4], signed=True)
        if change in (
            PlayStatusChange.TRACK_TIME_MS,
            PlayStatusChange.TRACK_TIME_S,
            PlayStatusChange.CHAPTER_TIME_MS,
            PlayStatusChange.CHAPTER_TIME_S,
            PlayStatusChange.PLAYBACK_ENGINE_CONTENTS,
        ):
            return _number(data[:4])
        if change == PlayStatusChange.TRACK_UID:
            return _number(data[:8])
        if change == PlayStatusChange.PLAYBACK_STATUS_EXTENDED:
            try:
                return ExtendedPlayState(data[0])
            except ValueError:
                return data[0]
        if change == PlayStatusChange.TRACK_PLAYBACK_MODE:
            try:
                return PlaybackMode(data[0])
            except ValueError:
                return data[0]
        if change == PlayStatusChange.TRACK_CAPABILITIES:
            return TrackCapability(_number(data[:4]))

        return data

    # --- playback -------------------------------------------------------------

    def get_play_status(self) -> PlayerStatus:
        """Get the player state and the current track's length and position"""

        data = self.request("GetPlayStatus", response="ReturnPlayStatus").data
        _check_length(data, 9, "play status")

        try:
            state = PlayerState(data[8])
        except ValueError:
            state = PlayerState.ERROR

        return PlayerStatus(_number(data[0:4]), _number(data[4:8]), state)

    def play_control(self, command: PlayControlCommand) -> None:
        """Control playback (play/pause, next, previous, seek, ...)"""

        self.request("PlayControl", encode_byte(command))

    def get_current_playing_track_index(self) -> int:
        """Get the Playback Engine index of the playing track, -1 if none is playing or paused"""

        response = self.request(
            "GetCurrentPlayingTrackIndex", response="ReturnCurrentPlayingTrackIndex"
        )
        _check_length(response.data, 4, "track index")
        return _number(response.data[:4], signed=True)

    def get_num_playing_tracks(self) -> int:
        """Get the number of tracks queued to play"""

        response = self.request("GetNumPlayingTracks", response="ReturnNumPlayingTracks")
        _check_length(response.data, 4, "playing tracks")
        return _number(response.data[:4])

    def set_current_playing_track(self, track_index: int) -> None:
        """Play the track at the given Playback Engine index (only while playing or paused)"""

        self.request("SetCurrentPlayingTrack", encode_int(track_index))

    def _indexed_track_string(self, command: str, response: str, track_index: int) -> str:
        return _string(self.request(command, encode_int(track_index), response=response).data)

    def get_indexed_playing_track_title(self, track_index: int) -> str:
        """Get the title of a track in the Playback Engine"""

        return self._indexed_track_string(
            "GetIndexedPlayingTrackTitle", "ReturnIndexedPlayingTrackTitle", track_index
        )

    def get_indexed_playing_track_artist_name(self, track_index: int) -> str:
        """Get the artist name of a track in the Playback Engine"""

        return self._indexed_track_string(
            "GetIndexedPlayingTrackArtistName", "ReturnIndexedPlayingTrackArtistName", track_index
        )

    def get_indexed_playing_track_album_name(self, track_index: int) -> str:
        """Get the album name of a track in the Playback Engine"""

        return self._indexed_track_string(
            "GetIndexedPlayingTrackAlbumName", "ReturnIndexedPlayingTrackAlbumName", track_index
        )

    def get_indexed_playing_track_info(
        self,
        info_type: PlayingTrackInfoType,
        track_index: int,
        chapter_index: int = 0,
        idle_timeout: float = 0.5,
    ) -> Any:
        """
        Get a type of information about a track in the Playback Engine

        Returns TrackCapsInfo for CAPS, datetime (or None) for RELEASE_DATE,
        {format ID: image count} for ARTWORK_COUNT, and a string for the
        others. Lyrics of the playing track may take up to 5 seconds to
        become available, see PlayStatusEvent.TRACK_LYRICS_READY.
        """

        info_type = PlayingTrackInfoType(info_type)
        data = encode_byte(info_type) + encode_int(track_index) + encode_short(chapter_index)

        if info_type in (PlayingTrackInfoType.DESCRIPTION, PlayingTrackInfoType.LYRICS):
            # Sent in sections: info type, packet info bits, packet index, text
            def done(packets: list[Packet]) -> bool:
                bits = packets[-1].data[1] if len(packets[-1].data) > 1 else 0
                return not bits & 0x01 or bool(bits & 0x02)

            packets = self.request_multiple(
                "GetIndexedPlayingTrackInfo",
                data,
                response="ReturnIndexedPlayingTrackInfo",
                done=done,
                idle_timeout=idle_timeout,
            )
            packets.sort(key=lambda p: _number(p.data[2:4]))
            return _string(b"".join(p.data[4:] for p in packets))

        info = self.request(
            "GetIndexedPlayingTrackInfo", data, response="ReturnIndexedPlayingTrackInfo"
        ).data[1:]

        if info_type == PlayingTrackInfoType.CAPS:
            _check_length(info, 10, "track caps")
            return TrackCapsInfo(
                TrackCapability(_number(info[0:4])), _number(info[4:8]), _number(info[8:10])
            )
        if info_type == PlayingTrackInfoType.RELEASE_DATE:
            return _datetime(info)
        if info_type == PlayingTrackInfoType.ARTWORK_COUNT:
            return {
                _number(info[i : i + 2]): _number(info[i + 2 : i + 4])
                for i in range(0, len(info) - 3, 4)
            }

        return _string(info)

    # --- chapters and audiobooks ----------------------------------------------

    def get_current_playing_track_chapter_info(self) -> ChapterInfo:
        """Get the playing track's chapter index and count"""

        response = self.request(
            "GetCurrentPlayingTrackChapterInfo", response="ReturnCurrentPlayingTrackChapterInfo"
        )
        _check_length(response.data, 8, "chapter info")
        return ChapterInfo(
            _number(response.data[0:4], signed=True), _number(response.data[4:8], signed=True)
        )

    def set_current_playing_track_chapter(self, chapter_index: int) -> None:
        """Play the given chapter of the playing track (only while playing or paused)"""

        self.request("SetCurrentPlayingTrackChapter", encode_int(chapter_index))

    def get_current_playing_track_chapter_play_status(
        self, chapter_index: int
    ) -> ChapterPlayStatus:
        """Get the length and elapsed time of a chapter of the playing track"""

        response = self.request(
            "GetCurrentPlayingTrackChapterPlayStatus",
            encode_int(chapter_index),
            response="ReturnCurrentPlayingTrackChapterPlayStatus",
        )
        _check_length(response.data, 8, "chapter play status")
        return ChapterPlayStatus(_number(response.data[0:4]), _number(response.data[4:8]))

    def get_current_playing_track_chapter_name(self, chapter_index: int) -> str:
        """Get the name of a chapter of the playing track"""

        response = self.request(
            "GetCurrentPlayingTrackChapterName",
            encode_int(chapter_index),
            response="ReturnCurrentPlayingTrackChapterName",
        )
        return _string(response.data)

    def get_audiobook_speed(self) -> AudiobookSpeed:
        response = self.request("GetAudiobookSpeed", response="ReturnAudiobookSpeed")
        _check_length(response.data, 1, "audiobook speed")
        return AudiobookSpeed(_number(response.data[:1], signed=True))

    def set_audiobook_speed(
        self, speed: AudiobookSpeed, restore_on_exit: bool | None = True
    ) -> None:
        """
        Set the audiobook playback speed

        - restore_on_exit: Restore the original speed when the accessory
          detaches (True) or keep it (False), for all audiobooks; None to
          change only the playing audiobook
        """

        data = encode_byte(speed, signed=True)
        if restore_on_exit is not None:
            data += encode_byte(int(restore_on_exit))

        self.request("SetAudiobookSpeed", data)

    # --- shuffle and repeat ---------------------------------------------------

    def get_shuffle(self) -> ShuffleMode:
        response = self.request("GetShuffle", response="ReturnShuffle")
        _check_length(response.data, 1, "shuffle")
        return ShuffleMode(response.data[0])

    def set_shuffle(self, mode: ShuffleMode, restore_on_exit: bool | None = True) -> None:
        """
        Set the shuffle mode, it only affects the Playback Engine

        - restore_on_exit: Restore the original mode when the accessory
          detaches (True), keep it (False), or None to send the command
          without the field (the mode is kept)
        """

        data = encode_byte(mode)
        if restore_on_exit is not None:
            data += encode_byte(int(restore_on_exit))

        self.request("SetShuffle", data)

    def get_repeat(self) -> RepeatMode:
        response = self.request("GetRepeat", response="ReturnRepeat")
        _check_length(response.data, 1, "repeat")
        return RepeatMode(response.data[0])

    def set_repeat(self, mode: RepeatMode, restore_on_exit: bool | None = True) -> None:
        """
        Set the repeat mode

        - restore_on_exit: Restore the original mode when the accessory
          detaches (True), keep it (False), or None to send the command
          without the field (the mode is kept)
        """

        data = encode_byte(mode)
        if restore_on_exit is not None:
            data += encode_byte(int(restore_on_exit))

        self.request("SetRepeat", data)

    # --- database -------------------------------------------------------------
    #
    # Selections are additive, each one narrows the records of the next
    # category (e.g. artist, then album, then track). Selecting a single
    # track passes the selection to the Playback Engine and starts playback.

    def reset_db_selection(self) -> None:
        """Clear the database selection and return to the top of the audio hierarchy"""

        self.request("ResetDBSelection")

    def reset_db_selection_hierarchy(self, hierarchy: DBHierarchy) -> None:
        """Clear the database selection and switch to the audio or video hierarchy"""

        self.request("ResetDBSelectionHierarchy", encode_byte(hierarchy))

    def select_db_record(self, category: DBCategory, record_index: int) -> None:
        """
        Select a record of a category, narrowing the database selection

        Index -1 undoes the selection of that category (one level up). The
        category's record count must have been read with
        get_number_categorized_db_records() first.
        """

        self.request(
            "SelectDBRecord", encode_byte(category) + encode_int(record_index, signed=True)
        )

    def get_number_categorized_db_records(self, category: DBCategory) -> int:
        """Get the number of records of a category in the current selection"""

        response = self.request(
            "GetNumberCategorizedDBRecords",
            encode_byte(category),
            response="ReturnNumberCategorizedDBRecords",
        )
        _check_length(response.data, 4, "record count")
        return _number(response.data[:4], signed=True)

    def retrieve_categorized_database_records(
        self,
        category: DBCategory,
        start: int = 0,
        count: int = -1,
        idle_timeout: float = 0.3,
    ) -> list[tuple[int, str]]:
        """
        Get the names of the records of a category, as (record index, name)

        - start: Index of the first record
        - count: Number of records, -1 for all records from start
        """

        if count == 0:
            return []

        packets = self.request_multiple(
            "RetrieveCategorizedDatabaseRecords",
            encode_byte(category) + encode_int(start, signed=True) + encode_int(count, signed=True),
            response="ReturnCategorizedDatabaseRecord",
            done=(lambda packets: len(packets) >= count) if count > 0 else None,
            idle_timeout=idle_timeout,
        )

        return [(_number(p.data[0:4]), _string(p.data[4:])) for p in packets if len(p.data) >= 4]

    def get_playlist_info(self, playlist_index: int) -> bool:
        """Whether the playlist at the given database index is a Genius playlist"""

        response = self.request(
            "GetPlaylistInfo",
            encode_byte(0x00) + encode_int(playlist_index),
            response="RetPlaylistInfo",
        )
        return bool(_number(response.data[1:]) & 0x01)

    def get_db_itunes_info(self, info_type: iTunesInfoType) -> Any:
        """
        Get iTunes database metadata

        Returns an int (the database UID or a count), or a datetime for LAST_SYNC.
        """

        response = self.request(
            "GetDBiTunesInfo", encode_byte(info_type), response="RetDBiTunesInfo"
        )
        info = response.data[1:]

        if info_type == iTunesInfoType.LAST_SYNC:
            return _datetime(info)

        return _number(info)

    # --- track information ----------------------------------------------------

    @staticmethod
    def encode_track_info_mask(bits: Iterable[TrackInfoBit]) -> bytes:
        """Encode a track information bitmask, byte 0 holds bits 0-7"""

        mask = 0
        for bit in bits:
            mask |= 1 << TrackInfoBit(bit)

        return mask.to_bytes(max(1, (mask.bit_length() + 7) // 8), "little")

    @staticmethod
    def decode_track_info(bit: TrackInfoBit, data: bytes) -> Any:
        """
        Decode the data of a track information type, see TrackInfoBit

        CHAPTER_TIMES and CHAPTER_NAMES return a list of pairs, LYRICS returns
        (section index, last section index, text bytes) as it may span packets.
        """

        if bit == TrackInfoBit.CAPABILITIES:
            return TrackCapability(_number(data[:4]))
        if bit in (
            TrackInfoBit.NAME,
            TrackInfoBit.ARTIST,
            TrackInfoBit.ALBUM,
            TrackInfoBit.GENRE,
            TrackInfoBit.COMPOSER,
            TrackInfoBit.DESCRIPTION,
            TrackInfoBit.SERIES_NAME,
        ):
            return _string(data)
        if bit == TrackInfoBit.UID:
            return _number(data[:8])
        if bit in (
            TrackInfoBit.CHAPTER_COUNT,
            TrackInfoBit.ALBUM_TRACK_INDEX,
            TrackInfoBit.DISC_SET_ALBUM_INDEX,
            TrackInfoBit.YEAR,
            TrackInfoBit.SEASON_NUMBER,
            TrackInfoBit.EQ_PRESET,
        ):
            return _number(data[:2])
        if bit in (
            TrackInfoBit.DURATION,
            TrackInfoBit.PLAY_COUNT,
            TrackInfoBit.SKIP_COUNT,
            TrackInfoBit.DATA_RATE,
            TrackInfoBit.BOOKMARK_OFFSET,
        ):
            return _number(data[:4])
        if bit == TrackInfoBit.CHAPTER_TIMES:
            return [
                (_number(data[i : i + 2]), _number(data[i + 2 : i + 6]))
                for i in range(0, len(data) - 5, 6)
            ]
        if bit == TrackInfoBit.CHAPTER_NAMES:
            names = []
            i = 0
            while i + 2 <= len(data):
                end = data.find(b"\x00", i + 2)
                end = len(data) if end < 0 else end
                names.append((_number(data[i : i + 2]), _string(data[i + 2 : end])))
                i = end + 1
            return names
        if bit == TrackInfoBit.LYRICS:
            return _number(data[0:2]), _number(data[2:4]), data[4:]
        if bit in (TrackInfoBit.PODCAST_RELEASE_DATE, TrackInfoBit.LAST_PLAYED):
            return _datetime(data)
        if bit == TrackInfoBit.STAR_RATING:
            return data[0]
        if bit == TrackInfoBit.VOLUME_ADJUST:
            return _number(data[:1], signed=True)
        if bit == TrackInfoBit.START_STOP_OFFSET:
            return _number(data[0:4]), _number(data[4:8])

        return data

    def _track_info(
        self,
        command: str,
        response: str,
        data: bytes,
        bits: Iterable[TrackInfoBit],
        key_size: int,
        tracks: int,
        idle_timeout: float,
    ) -> dict[int, dict[TrackInfoBit, Any]]:
        """Request track information, grouped by track index (or UID)"""

        bits = {TrackInfoBit(bit) for bit in bits}
        if not bits:
            return {}

        # Without the multi-packet types each track and type is one packet
        done = None
        if tracks >= 0 and not bits & self.MULTI_PACKET_BITS:
            expected = tracks * len(bits)
            done = lambda packets: len(packets) >= expected  # noqa: E731

        packets = self.request_multiple(
            command,
            data + self.encode_track_info_mask(bits),
            response=response,
            done=done,
            idle_timeout=idle_timeout,
        )

        result: dict[int, dict[TrackInfoBit, Any]] = {}
        lyrics: dict[int, list[tuple[int, bytes]]] = {}

        for packet in packets:
            if len(packet.data) < key_size + 1:
                continue

            key = _number(packet.data[:key_size])
            try:
                bit = TrackInfoBit(packet.data[key_size])
            except ValueError:
                continue

            value = self.decode_track_info(bit, packet.data[key_size + 1 :])
            info = result.setdefault(key, {})

            if bit in (TrackInfoBit.CHAPTER_TIMES, TrackInfoBit.CHAPTER_NAMES):
                info.setdefault(bit, []).extend(value)
            elif bit == TrackInfoBit.LYRICS:
                lyrics.setdefault(key, []).append((value[0], value[2]))
            else:
                info[bit] = value

        # Lyrics sections are parts of one string, joined in section order
        for key, sections in lyrics.items():
            text = b"".join(part for _, part in sorted(sections, key=lambda s: s[0]))
            result[key][TrackInfoBit.LYRICS] = _string(text)

        return result

    def get_uid_track_info(
        self, uid: int, bits: Iterable[TrackInfoBit], idle_timeout: float = 0.5
    ) -> dict[TrackInfoBit, Any]:
        """Get information about the track with the given UID, see TrackInfoBit"""

        bits = [bit for bit in bits if bit != TrackInfoBit.UID]
        info = self._track_info(
            "GetUIDTrackInfo", "RetUIDTrackInfo", encode_long(uid), bits, 8, 1, idle_timeout
        )
        return info.get(uid, {})

    def get_db_track_info(
        self,
        start: int,
        count: int,
        bits: Iterable[TrackInfoBit],
        idle_timeout: float = 0.5,
    ) -> dict[int, dict[TrackInfoBit, Any]]:
        """
        Get information about tracks of the database selection, as
        {track index: {info type: value}}

        - start: Index of the first track in the selection
        - count: Number of tracks, -1 for all tracks from start
        """

        return self._track_info(
            "GetDBTrackInfo",
            "RetDBTrackInfo",
            encode_int(start) + encode_int(count, signed=True),
            bits,
            4,
            count,
            idle_timeout,
        )

    def get_pb_track_info(
        self,
        start: int,
        count: int,
        bits: Iterable[TrackInfoBit],
        idle_timeout: float = 0.5,
    ) -> dict[int, dict[TrackInfoBit, Any]]:
        """
        Get information about tracks in the Playback Engine, as
        {track index: {info type: value}}

        - start: Playback index of the first track
        - count: Number of tracks, -1 for all tracks from start
        """

        return self._track_info(
            "GetPBTrackInfo",
            "RetPBTrackInfo",
            encode_int(start) + encode_int(count, signed=True),
            bits,
            4,
            count,
            idle_timeout,
        )

    # --- Genius ---------------------------------------------------------------

    def create_genius_playlist(
        self, index_type: IndexType, track_index: int, timeout: float = 30
    ) -> None:
        """Create a Genius playlist from a track and start playing it (takes up to 30 s)"""

        self.request(
            "CreateGeniusPlaylist",
            encode_byte(index_type) + encode_int(track_index),
            timeout=timeout,
        )

    def refresh_genius_playlist(self, playlist_index: int, timeout: float = 30) -> None:
        """
        Refresh a Genius playlist selected while browsing the database

        The iPod sends a General lingo iPodNotification when the refresh is complete.
        """

        self.request("RefreshGeniusPlaylist", encode_int(playlist_index), timeout=timeout)

    def is_genius_available_for_track(self, index_type: IndexType, track_index: int) -> bool:
        """Whether Genius information is available for a track"""

        try:
            self.request(
                "IsGeniusAvailableForTrack", encode_byte(index_type) + encode_int(track_index)
            )
        except iAPAckError as e:
            if e.status != self.ACK_NOT_GENIUS:
                raise
            return False

        return True

    # --- track UID lists ------------------------------------------------------

    def _data_budget(self) -> int:
        """Largest command data that fits a packet to the iPod"""

        if self._max_payload is None:
            self._max_payload = min(
                self.iap.transport.max_payload_size,
                self.iap.general.request_transport_max_payload_size(),
            )

        # Lingo ID, 2 byte command ID and the transaction ID
        overhead = 3 + (2 if self.iap.transaction_ids_enabled else 0)
        return self._max_payload - overhead

    def prepare_uid_list(self, uids: Iterable[int]) -> None:
        """
        Prepare a list of tracks (by UID) to play with play_prepared_uid_list()

        An empty list clears the prepared list.
        """

        uids = list(uids)
        per_section = max(1, (self._data_budget() - 4) // 8)
        sections = [
            uids[i : i + per_section] for i in range(0, len(uids), per_section)
        ] or [[]]
        last = len(sections) - 1

        # All sections share the transaction ID of the first
        transaction_id = (
            self.iap.next_transaction_id() if self.iap.transaction_ids_enabled else False
        )

        for index, section in enumerate(sections):
            data = encode_short(index) + encode_short(last)
            data += b"".join(encode_long(uid) for uid in section)

            try:
                self.request("PrepareUIDList", data, transaction_id=transaction_id)
            except iAPAckError as e:
                # Sections before the last are acknowledged as received
                if e.status != self.ACK_SECTION_RECEIVED or index == last:
                    raise

    def play_prepared_uid_list(self, uid: int) -> None:
        """Play the prepared list, starting with the track with the given UID"""

        self.request("PlayPreparedUIDList", encode_byte(0x00) + encode_long(uid))

    # --- artwork --------------------------------------------------------------
    #
    # Artwork exists in the formats returned by get_artwork_formats(), at the
    # times (offsets from the track start) returned by the artwork times
    # commands. Artwork.to_image() converts it to a Pillow image.

    def get_artwork_formats(self) -> list[ArtworkFormat]:
        """Get the artwork formats supported by the iPod"""

        data = self.request("GetArtworkFormats", response="RetArtworkFormats").data

        return [
            ArtworkFormat(
                _number(data[i : i + 2]),
                data[i + 2],
                _number(data[i + 3 : i + 5]),
                _number(data[i + 5 : i + 7]),
            )
            for i in range(0, len(data) - 6, 7)
        ]

    def get_track_artwork_times(
        self, track_index: int, format_id: int, artwork_index: int = 0, count: int = -1
    ) -> list[int]:
        """
        Get the times (ms from the track start) of a playing track's artwork

        - artwork_index: First artwork to return
        - count: Maximum number of times, -1 for no limit
        """

        response = self.request(
            "GetTrackArtworkTimes",
            encode_int(track_index)
            + encode_short(format_id)
            + encode_short(artwork_index)
            + encode_short(count, signed=True),
            response="RetTrackArtworkTimes",
        )
        data = response.data
        return [_number(data[i : i + 4]) for i in range(0, len(data) - 3, 4)]

    @staticmethod
    def _parse_artwork(description: bytes, pixels: bytes) -> Artwork:
        """Parse an image description (format, size, inset, row size) and its pixel data"""

        _check_length(description, 17, "artwork")
        return Artwork(
            description[0],
            _number(description[1:3]),
            _number(description[3:5]),
            tuple(_number(description[i : i + 2]) for i in range(5, 13, 2)),  # type: ignore[arg-type]
            _number(description[13:17]),
            pixels,
        )

    def get_track_artwork_data(
        self, track_index: int, format_id: int, time_ms: int, idle_timeout: float = 0.5
    ) -> Artwork:
        """Get a playing track's artwork in a format, at a time from get_track_artwork_times()"""

        def received(packets: list[Packet]) -> int:
            return sum(len(p.data) - 2 for p in packets) - 17

        def done(packets: list[Packet]) -> bool:
            first = next((p for p in packets if p.data[:2] == b"\x00\x00"), None)
            if first is None or len(first.data) < 19:
                return False
            size = _number(first.data[15:19]) * _number(first.data[5:7])
            return received(packets) >= size

        packets = self.request_multiple(
            "GetTrackArtworkData",
            encode_int(track_index) + encode_short(format_id) + encode_int(time_ms),
            response="RetTrackArtworkData",
            done=done,
            idle_timeout=idle_timeout,
        )

        # Descriptor packet index 0, then data packets with increasing indexes
        packets.sort(key=lambda p: _number(p.data[0:2]))
        first = packets[0].data
        _check_length(first, 19, "track artwork")

        pixels = first[19:] + b"".join(p.data[2:] for p in packets[1:])
        return self._parse_artwork(first[2:19], pixels)

    @staticmethod
    def _encode_track_identifier(identifier_type: TrackIdentifierType, identifier: int) -> bytes:
        if identifier_type == TrackIdentifierType.UID:
            return encode_byte(identifier_type) + encode_long(identifier)

        return encode_byte(identifier_type) + encode_int(identifier)

    def get_artwork_times(
        self,
        identifier_type: TrackIdentifierType,
        identifier: int,
        format_id: int,
        artwork_index: int = 0,
        count: int = -1,
    ) -> list[int]:
        """
        Get the times (ms from the track start) of a track's artwork

        - identifier_type, identifier: Track UID, playback index or database index
        - artwork_index: First artwork to return
        - count: Maximum number of times, -1 for no limit
        """

        response = self.request(
            "GetArtworkTimes",
            self._encode_track_identifier(identifier_type, identifier)
            + encode_short(format_id)
            + encode_short(artwork_index)
            + encode_short(count, signed=True),
            response="RetArtworkTimes",
        )

        data = response.data
        offset = 9 if data[:1] == encode_byte(TrackIdentifierType.UID) else 5
        return [_number(data[i : i + 4]) for i in range(offset, len(data) - 3, 4)]

    def get_artwork_data(
        self,
        identifier_type: TrackIdentifierType,
        identifier: int,
        format_id: int,
        time_ms: int,
        idle_timeout: float = 0.5,
    ) -> Artwork:
        """
        Get a track's artwork in a format, at a time from get_artwork_times()

        - identifier_type, identifier: Track UID, playback index or database index
        """

        def done(packets: list[Packet]) -> bool:
            last = _number(packets[-1].data[2:4])
            return len({_number(p.data[0:2]) for p in packets}) > last

        packets = self.request_multiple(
            "GetArtworkData",
            self._encode_track_identifier(identifier_type, identifier)
            + encode_short(format_id)
            + encode_int(time_ms),
            response="RetArtworkData",
            done=done,
            idle_timeout=idle_timeout,
        )

        # Sections carry sectCur and sectMax, then their part of the payload
        packets.sort(key=lambda p: _number(p.data[0:2]))
        payload = b"".join(p.data[4:] for p in packets)

        # The payload starts with the track identifier. The spec's table of
        # the image description omits the height, but it has the same layout
        # as RetTrackArtworkData's descriptor.
        offset = 9 if payload[:1] == encode_byte(TrackIdentifierType.UID) else 5
        return self._parse_artwork(payload[offset : offset + 17], payload[offset + 17 :])

    # --- display image --------------------------------------------------------

    def get_mono_display_image_limits(self) -> DisplayImageLimits:
        """Get the largest monochrome image accepted by set_display_image()"""

        response = self.request(
            "GetMonoDisplayImageLimits", response="ReturnMonoDisplayImageLimits"
        )
        data = response.data
        _check_length(data, 5, "display image limits")
        return DisplayImageLimits(_number(data[0:2]), _number(data[2:4]), data[4])

    def get_color_display_image_limits(self) -> list[DisplayImageLimits]:
        """Get the largest color image per pixel format, only for iPods with color displays"""

        response = self.request(
            "GetColorDisplayImageLimits", response="ReturnColorDisplayImageLimits"
        )
        data = response.data
        return [
            DisplayImageLimits(_number(data[i : i + 2]), _number(data[i + 2 : i + 4]), data[i + 4])
            for i in range(0, len(data) - 4, 5)
        ]

    def set_display_image_data(
        self,
        pixel_format: PixelFormat,
        width: int,
        height: int,
        data: bytes,
        row_size: int | None = None,
    ) -> None:
        """
        Set the image shown on the iPod's "OK to disconnect" screen from raw
        pixel data, see set_display_image()

        - data: Pixel data, row_size * height bytes
        - row_size: Bytes per row, None for the size padded to 32 bits
        """

        if row_size is None:
            row_size = image_row_size(pixel_format, width)

        if len(data) < row_size * height:
            raise ValueError(
                f"Image data is {len(data)} bytes, {row_size * height} expected"
            )
        data = data[: row_size * height]

        # Descriptor packet (index 0) with the start of the data, then data packets
        budget = self._data_budget() - 2
        descriptor = (
            encode_byte(pixel_format) + encode_short(width) + encode_short(height) + encode_int(row_size)
        )

        first = budget - len(descriptor)
        chunks = [descriptor + data[:first]]
        chunks += [data[i : i + budget] for i in range(first, len(data), budget)]

        for index, chunk in enumerate(chunks):
            self.request("SetDisplayImage", encode_short(index) + chunk)

    def set_display_image(self, image: "Image", pixel_format: PixelFormat | None = None) -> None:
        """
        Set the image shown on the iPod's "OK to disconnect" screen, needs Pillow

        The image is scaled down to fit the iPod's limits. Deprecated by Apple,
        newer iPods may ignore it; some only show it within 15 s of entering
        Extended Interface mode.

        - pixel_format: Pixel format to send, None for color if supported
        """

        limits = self._display_image_limits(pixel_format)

        if image.width > limits.width or image.height > limits.height:
            image = image.copy()
            image.thumbnail((limits.width, limits.height))

        stride, data = encode_image(image, limits.pixel_format)
        self.set_display_image_data(
            PixelFormat(limits.pixel_format), image.width, image.height, data, stride
        )

    def _display_image_limits(self, pixel_format: PixelFormat | None) -> DisplayImageLimits:
        if pixel_format != PixelFormat.MONO_2BPP:
            try:
                for limits in self.get_color_display_image_limits():
                    if pixel_format is None or limits.pixel_format == pixel_format:
                        return limits
            except iAPAckError:
                # Only iPods with color displays support the color limits
                if pixel_format is not None:
                    raise

            if pixel_format is not None:
                raise ValueError(f"The iPod doesn't support pixel format {pixel_format!r}")

        return self.get_mono_display_image_limits()

    # --- deprecated -----------------------------------------------------------

    def request_protocol_version(self) -> tuple[int, int]:
        """
        Get the Extended Interface protocol version (major, minor)

        Deprecated except for 3G iPods, use General.request_lingo_protocol_version()
        """

        response = self.request("RequestProtocolVersion", response="ReturnProtocolVersion")
        _check_length(response.data, 2, "protocol version")
        return response.data[0], response.data[1]

    def request_ipod_name(self) -> str:
        """
        Get the name of the iPod

        Deprecated except for 3G iPods, use General.request_ipod_name()
        """

        return _string(self.request("RequestiPodName", response="ReturniPodName").data)

    def play_current_selection(self, track_index: int) -> None:
        """
        Play the database selection, starting with the given track

        Deprecated, use select_db_record() with DBCategory.TRACK
        """

        self.request("PlayCurrentSelection", encode_int(track_index, signed=True))

    def select_sort_db_record(
        self, category: DBCategory, record_index: int, sort: SortOrder = SortOrder.DEFAULT
    ) -> None:
        """
        Select a record like select_db_record(), sorting the selected tracks

        Deprecated, use select_db_record()
        """

        self.request(
            "SelectSortDBRecord",
            encode_byte(category) + encode_int(record_index, signed=True) + encode_byte(sort),
        )
