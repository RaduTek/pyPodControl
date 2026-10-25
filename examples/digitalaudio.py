import argparse
import sys

from common import add_transport_args, make_auth, make_transport
from pypodcontrol import iAPClient
from pypodcontrol.audio import AudioError, create_audio_router
from pypodcontrol.lingo import DigitalAudio, DisplayRemote, RemoteEvent, TrackInfoType


def digital_audio():
    parser = argparse.ArgumentParser(
        description="Route the iPod's digital audio over USB to the computer's output, "
        "tracking the iPod's volume"
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "pipewire", "jack"),
        default="auto",
        help="Audio routing backend (default: %(default)s)",
    )
    parser.add_argument(
        "--sink",
        default=None,
        help="Output sink/target to route to (default: the system default output)",
    )
    add_transport_args(parser)
    args = parser.parse_args()

    if not args.usb:
        parser.error("Digital audio needs the USB transport (the iPod USB Interface); pass --usb")

    with iAPClient(make_transport(args), auth=make_auth(args)) as iap:
        da = iap.register(DigitalAudio)
        dr = iap.register(DisplayRemote)
        iap.start_identify()

        def on_attributes(attributes):
            print(f"Track sample rate: {attributes.sample_rate} Hz")
            # The iPod streams only at this rate, so match the output to it
            router.set_rate(attributes.sample_rate)

        da.add_track_attributes_listener(on_attributes)

        router = create_audio_router(args.backend)
        print("Waiting for the iPod's audio source, start playback on the iPod...")
        try:
            router.start(args.sink)
        except AudioError as e:
            print(f"Could not route audio: {e}", file=sys.stderr)
            return

        # If a track's rate was already reported during setup, apply it now
        if da.sample_rate is not None:
            router.set_rate(da.sample_rate)

        def on_volume(event, volume):
            router.set_muted(volume.muted)
            level = 0.0 if volume.muted else volume.ui_level / 255
            router.set_volume(level)
            if volume.muted:
                print("Volume: muted")
            else:
                print(f"Volume: {level * 100:.0f}%")

        def print_track(index: int) -> None:
            # Listeners run on the client's event thread, so they can send requests
            title = dr.get_track_text(TrackInfoType.TITLE, index)
            artist = dr.get_track_text(TrackInfoType.ARTIST, index)
            album = dr.get_track_text(TrackInfoType.ALBUM, index)
            print(f"Track {index + 1}: {title} - {artist} ({album})")

        def on_track(event, index):
            print_track(index)
        
        dr.add_event_listener(RemoteEvent.ABSOLUTE_VOLUME, on_volume)
        dr.add_event_listener(RemoteEvent.VOLUME, on_volume)
        dr.add_event_listener(RemoteEvent.TRACK_INDEX, on_track)
        dr.set_remote_event_notification(
            [RemoteEvent.ABSOLUTE_VOLUME, RemoteEvent.PLAY_STATE, RemoteEvent.TRACK_INDEX]
        )

        print("Audio routed, adjust the volume on the iPod. Press Ctrl+C to quit")

        try:
            iap.wait_until_closed()
            print("iPod disconnected")
        except KeyboardInterrupt:
            pass
        finally:
            router.stop()


if __name__ == "__main__":
    digital_audio()
