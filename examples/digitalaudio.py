import argparse
import os
import select
import shutil
import sys
import termios
import threading
import time
import tty

from common import add_transport_args, make_auth, make_transport
from pypodcontrol import iAPClient
from pypodcontrol.audio import AudioError, create_audio_router
from pypodcontrol.errors import iAPAckError
from pypodcontrol.lingo import (
    DigitalAudio,
    DisplayRemote,
    PlayState,
    RemoteEvent,
    SimpleRemote,
    TrackInfoType,
    Volume,
)
from pypodcontrol.packet import encode_byte

# Keys that drive the iPod through the Simple Remote lingo. Arrow keys are
# handled separately (they arrive as escape sequences), see read_keys().
KEYMAP = {
    " ": "play_pause",
    "p": "play_pause",
    "x": "stop",
    "n": "next_track",
    "b": "previous_track",
    "N": "next_album",
    "B": "previous_album",
    "+": "volume_up",
    "=": "volume_up",
    "-": "volume_down",
    "_": "volume_down",
    "m": "mute",
    "s": "shuffle",
    "r": "repeat",
}
ARROW_BUTTONS = {
    "RIGHT": "next_track",
    "LEFT": "previous_track",
    "UP": "volume_up",
    "DOWN": "volume_down",
}

# The iPod reports shuffle and repeat as a small integer; label it for display
SHUFFLE_LABELS = {0: "off", 1: "songs", 2: "albums"}
REPEAT_LABELS = {0: "off", 1: "one", 2: "all"}
STATE_LABELS = {
    PlayState.STOPPED: "⏹ Stopped",
    PlayState.PLAYING: "▶ Playing",
    PlayState.PAUSED: "⏸ Paused",
    PlayState.FAST_FORWARD: "⏩ Fast-forward",
    PlayState.REWIND: "⏪ Rewind",
    PlayState.END_FAST_FORWARD_REWIND: "▶ Playing",
}

# ANSI escape codes for the full-screen, redraw-in-place display
ESC = "\x1b"
RESET = ESC + "[0m"


def sgr(*codes: int) -> str:
    """Build a Select Graphic Rendition (color/style) escape"""

    return ESC + "[" + ";".join(str(c) for c in codes) + "m"


BOLD = sgr(1)
DIM = sgr(2)
CYAN = sgr(36)
GREEN = sgr(32)
YELLOW = sgr(33)
WHITE = sgr(97)


class NowPlaying:
    """
    The current playback state the display draws, updated from the iPod's
    remote event notifications on the client's event thread

    Fields are read on the main (render) thread, so every access is guarded by
    the lock. The track position is stored with the moment it was captured so
    the progress bar can advance smoothly between the iPod's one-second updates.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.play_state: PlayState | None = None
        self.track_index: int | None = None
        self.total_tracks: int | None = None
        self.title = ""
        self.artist = ""
        self.album = ""
        self.genre = ""
        self.composer = ""
        self.length_ms = 0
        self.position_ms = 0
        self._position_ts = time.monotonic()
        self.volume: Volume | None = None
        self.shuffle: int | None = None
        self.repeat: int | None = None
        self.status = ""

    def set_position(self, position_ms: int) -> None:
        self.position_ms = position_ms
        self._position_ts = time.monotonic()

    def current_position_ms(self) -> int:
        """The track position now, extrapolated while playing"""

        position = self.position_ms
        if self.play_state == PlayState.PLAYING:
            position += int((time.monotonic() - self._position_ts) * 1000)
        if self.length_ms:
            position = min(position, self.length_ms)
        return max(position, 0)


def format_time(ms: int) -> str:
    """Milliseconds as M:SS (or H:MM:SS for long tracks)"""

    seconds = max(ms, 0) // 1000
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if hours:
        return f"{hours}:{minutes:02}:{seconds:02}"
    return f"{minutes}:{seconds:02}"


def field(text: str, width: int, color: str = "") -> str:
    """Truncate or pad plain text to an exact visible width, then colorize"""

    if len(text) > width:
        text = text[: max(width - 1, 0)] + "…"
    text = text.ljust(width)
    return f"{color}{text}{RESET}" if color else text


def split_row(left: str, right: str, width: int) -> str:
    """Left- and right-aligned plain text on one line of the given width"""

    gap = width - len(left) - len(right)
    if gap < 1:
        # No room for both; keep the left side and drop the right
        return field(left, width)
    return left + " " * gap + right


def progress_line(position_ms: int, length_ms: int, width: int) -> str:
    """A two-tone progress bar flanked by the elapsed and total times"""

    left = format_time(position_ms)
    right = format_time(length_ms) if length_ms else "--:--"
    bar_width = max(width - len(left) - len(right) - 2, 1)

    frac = position_ms / length_ms if length_ms else 0.0
    filled = min(max(round(bar_width * frac), 0), bar_width)
    bar = GREEN + "━" * filled + DIM + "─" * (bar_width - filled) + RESET

    return f"{DIM}{left}{RESET} {bar} {DIM}{right}{RESET}"


def volume_line(volume: Volume | None, width: int) -> str:
    """A volume meter with the level as a percentage (or muted)"""

    label = "Vol "
    if volume is None:
        text = "--"
        level = 0.0
    elif volume.muted:
        text = "muted"
        level = 0.0
    else:
        percent = volume.ui_level * 100 // 255
        text = f"{percent}%"
        level = volume.ui_level / 255

    bar_width = max(width - len(label) - len(text) - 1, 1)
    filled = min(max(round(bar_width * level), 0), bar_width)
    color = DIM if (volume is None or volume.muted) else GREEN
    bar = color + "▓" * filled + DIM + "░" * (bar_width - filled) + RESET

    return f"{WHITE}{label}{RESET}{bar} {text}"


def render(state: NowPlaying) -> str:
    """Build the whole screen as a string, read from a snapshot of the state"""

    with state.lock:
        play_state = state.play_state
        track_index = state.track_index
        total_tracks = state.total_tracks
        title = state.title
        artist = state.artist
        album = state.album
        genre = state.genre
        composer = state.composer
        length_ms = state.length_ms
        position_ms = state.current_position_ms()
        volume = state.volume
        shuffle = state.shuffle
        repeat = state.repeat
        status = state.status

    cols = shutil.get_terminal_size((80, 24)).columns
    width = max(min(cols, 72), 40)
    inner = width - 4  # borders and one space of padding on each side

    def line(content: str | None = None) -> str:
        # content is already exactly `inner` cells wide; a bare line() is blank
        if content is None:
            content = " " * inner
        return f"{DIM}│{RESET} {content} {DIM}│{RESET}"

    top = f"{DIM}┌─{RESET} {BOLD}{CYAN}pyPodControl · Digital Audio{RESET} "
    top += DIM + "─" * (width - len("┌─ pyPodControl · Digital Audio ") - 1) + "┐" + RESET
    divider = f"{DIM}├{'─' * (width - 2)}┤{RESET}"
    bottom = f"{DIM}└{'─' * (width - 2)}┘{RESET}"

    lines = [top, line()]

    if play_state in (None, PlayState.STOPPED):
        lines.append(line(field("Nothing playing", inner, DIM)))
        lines.append(line())
    else:
        lines.append(line(field(title or "(unknown)", inner, BOLD + WHITE)))
        lines.append(line(field(artist or "(unknown artist)", inner, CYAN)))
        lines.append(line(field(album or "(unknown album)", inner, DIM)))
        # Extra fields only when the iPod actually returned them
        for label, value in (("Genre", genre), ("Composer", composer)):
            if value:
                lines.append(line(field(f"{label}: {value}", inner, DIM)))
        lines.append(line())

        if track_index is not None:
            position = f"Track {track_index + 1}"
            if total_tracks:
                position += f" / {total_tracks}"
            lines.append(line(field(position, inner, YELLOW)))
            lines.append(line())

    # Play state with the shuffle and repeat modes
    state_text = STATE_LABELS.get(play_state, "·") if play_state is not None else "·"
    modes = ""
    if repeat is not None:
        modes += f"⟳ repeat {REPEAT_LABELS.get(repeat, repeat)}"
    if shuffle is not None:
        modes += ("   " if modes else "") + f"⤮ shuffle {SHUFFLE_LABELS.get(shuffle, shuffle)}"
    lines.append(line(split_row(state_text, modes, inner)))
    lines.append(line())

    lines.append(line(progress_line(position_ms, length_ms, inner)))
    lines.append(line())
    lines.append(line(volume_line(volume, inner)))
    lines.append(line())

    lines.append(divider)
    help1 = "space play/pause   ←/→ or n/b track   N/B album   x stop"
    help2 = "↑/↓ or +/- volume   m mute   s shuffle   r repeat   q quit"
    lines.append(line(field(help1, inner, DIM)))
    lines.append(line(field(help2, inner, DIM)))
    if status:
        lines.append(line(field(status, inner, GREEN)))
    lines.append(bottom)

    # Redraw in place: home the cursor, clear each line to its end, then clear
    # whatever is left below. This avoids the flicker of a full screen clear.
    out = ESC + "[H"
    out += (ESC + "[K\r\n").join(lines)
    out += ESC + "[K" + ESC + "[J"
    return out


def poll_state_info(dr: DisplayRemote, event: RemoteEvent):
    """
    Ask the iPod for one piece of state now, instead of waiting for it to
    notify a change

    GetiPodStateInfo echoes the info type and then the same payload the matching
    remote event carries, so decode_remote_event() understands it. Returns None
    if the iPod does not report this one.
    """

    try:
        response = dr.request(
            "GetiPodStateInfo", encode_byte(int(event)), response="RetiPodStateInfo"
        )
    except Exception:
        return None

    data = response.data
    if not data or data[0] != int(event):
        return None
    return DisplayRemote.decode_remote_event(event, data[1:])


def read_keys() -> list[str]:
    """
    Read the keys waiting on stdin, mapping arrow keys to their names

    Returns a list of tokens: single characters, or "UP"/"DOWN"/"LEFT"/"RIGHT".
    Reads the whole buffer at once so a pasted escape sequence stays together.
    """

    data = os.read(sys.stdin.fileno(), 32)
    keys: list[str] = []
    i = 0
    while i < len(data):
        if data[i : i + 2] == b"\x1b[" and i + 2 < len(data):
            keys.append({"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}.get(
                chr(data[i + 2]), ""
            ))
            i += 3
        else:
            keys.append(chr(data[i]))
            i += 1
    return [k for k in keys if k]


def digital_audio():
    parser = argparse.ArgumentParser(
        description="Route the iPod's digital audio over USB to the computer's output, "
        "with a now-playing display and keyboard remote control"
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
        sr = iap.register(SimpleRemote)
        iap.start_identify()

        router = create_audio_router(args.backend)

        def on_attributes(attributes):
            # The iPod streams only at this rate, so match the output to it
            router.set_rate(attributes.sample_rate)

        da.add_track_attributes_listener(on_attributes)

        print("Waiting for the iPod's audio source, start playback on the iPod...")
        try:
            router.start(args.sink)
        except AudioError as e:
            print(f"Could not route audio: {e}", file=sys.stderr)
            return

        # If a track's rate was already reported during setup, apply it now
        if da.sample_rate is not None:
            router.set_rate(da.sample_rate)

        state = NowPlaying()

        def apply_volume(volume: Volume) -> None:
            router.set_muted(volume.muted)
            router.set_volume(0.0 if volume.muted else volume.ui_level / 255)

        def refresh_track(index: int) -> None:
            # Runs on the event thread, so it may send requests to the iPod
            title = dr.get_track_text(TrackInfoType.TITLE, index)
            artist = dr.get_track_text(TrackInfoType.ARTIST, index)
            album = dr.get_track_text(TrackInfoType.ALBUM, index)
            genre = dr.get_track_text(TrackInfoType.GENRE, index)
            composer = dr.get_track_text(TrackInfoType.COMPOSER, index)
            status = dr.get_play_status()
            total = dr.get_num_playing_tracks()
            with state.lock:
                state.track_index = index
                state.total_tracks = total or None
                state.title = title
                state.artist = artist
                state.album = album
                state.genre = genre
                state.composer = composer
                state.length_ms = status.track_length_ms
                state.set_position(status.track_position_ms)

        def on_track(event, index):
            refresh_track(index)

        def on_play_state(event, play_state):
            with state.lock:
                # Re-anchor the extrapolated position when playback pauses/resumes
                state.position_ms = state.current_position_ms()
                state._position_ts = time.monotonic()
                state.play_state = play_state

        def on_position(event, seconds):
            with state.lock:
                state.set_position(seconds * 1000)

        def on_position_ms(event, ms):
            with state.lock:
                state.set_position(ms)

        def on_volume(event, volume):
            apply_volume(volume)
            with state.lock:
                state.volume = volume

        def on_shuffle(event, value):
            with state.lock:
                state.shuffle = value

        def on_repeat(event, value):
            with state.lock:
                state.repeat = value

        def on_tracks(event, count):
            with state.lock:
                state.total_tracks = count

        dr.add_event_listener(RemoteEvent.TRACK_INDEX, on_track)
        dr.add_event_listener(RemoteEvent.PLAY_STATE, on_play_state)
        dr.add_event_listener(RemoteEvent.TRACK_POSITION_S, on_position)
        dr.add_event_listener(RemoteEvent.TRACK_POSITION_MS, on_position_ms)
        dr.add_event_listener(RemoteEvent.ABSOLUTE_VOLUME, on_volume)
        dr.add_event_listener(RemoteEvent.VOLUME, on_volume)
        dr.add_event_listener(RemoteEvent.SHUFFLE, on_shuffle)
        dr.add_event_listener(RemoteEvent.REPEAT, on_repeat)
        dr.add_event_listener(RemoteEvent.PLAYBACK_ENGINE_CONTENTS, on_tracks)

        # Seed the display from the iPod's current state; the notifications
        # below only report later changes. A stopped iPod reports its track
        # fields as all-ones sentinels, so only trust them while it is playing.
        try:
            status = dr.get_play_status()
            total = dr.get_num_playing_tracks()
            with state.lock:
                state.play_state = status.state
                state.total_tracks = total or None
                if status.state != PlayState.STOPPED:
                    state.length_ms = status.track_length_ms
                    state.set_position(status.track_position_ms)
            if status.state != PlayState.STOPPED:
                refresh_track(status.track_index)
        except Exception:
            pass

        # Set the USB audio input gain from the iPod's volume straight away,
        # rather than waiting for the iPod to send a volume change.
        volume = poll_state_info(dr, RemoteEvent.VOLUME)
        if isinstance(volume, Volume):
            apply_volume(volume)
            with state.lock:
                state.volume = volume
        with state.lock:
            state.shuffle = poll_state_info(dr, RemoteEvent.SHUFFLE)
            state.repeat = poll_state_info(dr, RemoteEvent.REPEAT)

        # The iPod rejects the whole request if it does not support every event
        # in the mask. Ask for the rich set, but fall back to the classic events
        # that the earliest Display Remote lingo already had when it is refused
        # (per-second position, absolute volume and playback-engine contents
        # were added in later revisions). Listeners for both variants are
        # registered above, so only the enabled ones ever fire.
        rich = [
            RemoteEvent.TRACK_INDEX,
            RemoteEvent.PLAY_STATE,
            RemoteEvent.TRACK_POSITION_S,
            RemoteEvent.ABSOLUTE_VOLUME,
            RemoteEvent.SHUFFLE,
            RemoteEvent.REPEAT,
            RemoteEvent.PLAYBACK_ENGINE_CONTENTS,
        ]
        classic = [
            RemoteEvent.TRACK_INDEX,
            RemoteEvent.PLAY_STATE,
            RemoteEvent.TRACK_POSITION_MS,
            RemoteEvent.VOLUME,
            RemoteEvent.SHUFFLE,
            RemoteEvent.REPEAT,
        ]
        try:
            dr.set_remote_event_notification(rich)
        except iAPAckError:
            dr.set_remote_event_notification(classic)

        run_tui(iap, sr, state)
        router.stop()


def run_tui(iap: iAPClient, sr: SimpleRemote, state: NowPlaying) -> None:
    """Draw the display and translate key presses into remote button presses"""

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    sys.stdout.write(ESC + "[?1049h" + ESC + "[?25l")  # alt screen, hide cursor
    sys.stdout.flush()

    try:
        while iap.transport.is_open:
            sys.stdout.write(render(state))
            sys.stdout.flush()

            # Wake up ~4x a second so the progress bar keeps moving even when
            # the iPod is quiet, and respond to keys promptly in between.
            if not select.select([fd], [], [], 0.25)[0]:
                continue

            quit_requested = False
            for key in read_keys():
                if key == "q":
                    quit_requested = True
                    break

                button = ARROW_BUTTONS.get(key) if key in ARROW_BUTTONS else KEYMAP.get(key)
                if button is None:
                    continue

                with state.lock:
                    state.status = f"→ {button.replace('_', ' ')}"
                sr.press_button(button)

            if quit_requested:
                break
    finally:
        sys.stdout.write(ESC + "[?25h" + ESC + "[?1049l")  # show cursor, main screen
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSAFLUSH, saved)

    print("iPod disconnected" if not iap.transport.is_open else "Bye, bye!")


if __name__ == "__main__":
    digital_audio()
