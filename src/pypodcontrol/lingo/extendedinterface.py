from .. import iAPClient
from . import Lingo


class ExtendedInterface(Lingo):
    """
    ### Extended Interface Lingo (0x04)

    Request high power use from iPod
    """

    lingo_id = 0x04

    commands = {
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
    }
    """Available commands"""

    def __init__(self, iap: iAPClient) -> None:
        """Create a new instance of ExtendedInterface"""

        super().__init__(iap)
