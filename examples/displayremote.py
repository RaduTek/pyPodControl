import argparse

from common import add_transport_args, make_auth, make_transport
from pypodcontrol import iAPClient
from pypodcontrol.lingo import DisplayRemote, PlayState, RemoteEvent, TrackInfoType


def display_remote():
    parser = argparse.ArgumentParser(
        description="Print the iPod's track changes, play state and volume as they happen"
    )
    parser.add_argument(
        "--position", action="store_true", help="Also print the track position every second"
    )
    add_transport_args(parser)
    args = parser.parse_args()

    with iAPClient(make_transport(args), auth=make_auth(args)) as iap:
        dr = iap.register(DisplayRemote)
        iap.start_identify()

        def print_track(index: int) -> None:
            # Listeners run on the client's event thread, so they can send requests
            title = dr.get_track_text(TrackInfoType.TITLE, index)
            artist = dr.get_track_text(TrackInfoType.ARTIST, index)
            album = dr.get_track_text(TrackInfoType.ALBUM, index)
            print(f"Track {index + 1}: {title} - {artist} ({album})")

        def on_track(event, index):
            print_track(index)

        def on_play_state(event, state):
            print("State:", state.name.lower() if isinstance(state, PlayState) else state)

        def on_volume(event, volume):
            if volume.muted:
                print("Volume: muted")
            else:
                print(f"Volume: {volume.ui_level * 100 // 255}% (absolute {volume.absolute_level})")

        def on_position(event, seconds):
            print(f"Position: {seconds // 60}:{seconds % 60:02}")

        dr.add_event_listener(RemoteEvent.TRACK_INDEX, on_track)
        dr.add_event_listener(RemoteEvent.PLAY_STATE, on_play_state)
        dr.add_event_listener(RemoteEvent.ABSOLUTE_VOLUME, on_volume)

        events = [RemoteEvent.TRACK_INDEX, RemoteEvent.PLAY_STATE, RemoteEvent.ABSOLUTE_VOLUME]
        if args.position:
            dr.add_event_listener(RemoteEvent.TRACK_POSITION_S, on_position)
            events.append(RemoteEvent.TRACK_POSITION_S)

        # The current state, the notifications only report changes
        status = dr.get_play_status()
        print("State:", status.state.name.lower())
        if status.state != PlayState.STOPPED:
            print_track(status.track_index)

        dr.set_remote_event_notification(events)
        print("Waiting for events, press Ctrl+C to quit")

        try:
            iap.wait_until_closed()
            print("iPod disconnected")
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    display_remote()
