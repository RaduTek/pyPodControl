import argparse
import curses
import logging
import threading
import time
from dataclasses import dataclass, field

from common import add_transport_args, make_auth, make_transport
from pypodcontrol import iAPClient, iAPError
from pypodcontrol.lingo import (
    DBCategory,
    ExtendedInterface,
    ExtendedPlayState,
    PlayControlCommand,
    PlayerState,
    PlayStatusChange,
    PlayStatusEvent,
    RepeatMode,
    ShuffleMode,
)

ROOT = [
    ("Playlists", DBCategory.PLAYLIST),
    ("Artists", DBCategory.ARTIST),
    ("Albums", DBCategory.ALBUM),
    ("Genres", DBCategory.GENRE),
    ("Songs", DBCategory.TRACK),
    ("Composers", DBCategory.COMPOSER),
    ("Audiobooks", DBCategory.AUDIOBOOK),
    ("Podcasts", DBCategory.PODCAST),
]
"""Categories listed at the top of the browser"""

NEXT_CATEGORY = {
    DBCategory.PLAYLIST: DBCategory.TRACK,
    DBCategory.ARTIST: DBCategory.ALBUM,
    DBCategory.ALBUM: DBCategory.TRACK,
    DBCategory.GENRE: DBCategory.ARTIST,
    DBCategory.COMPOSER: DBCategory.ALBUM,
    DBCategory.PODCAST: DBCategory.TRACK,
}
"""Category listed after selecting a record, tracks and audiobooks play when selected"""

STATE_LABELS = {
    PlayerState.STOPPED: "■ Stopped",
    PlayerState.PLAYING: "▶ Playing",
    PlayerState.PAUSED: "‖ Paused",
    PlayerState.ERROR: "! Error",
}

EXTENDED_STATES = {
    ExtendedPlayState.STOPPED: PlayerState.STOPPED,
    ExtendedPlayState.PLAYING: PlayerState.PLAYING,
    ExtendedPlayState.PAUSED: PlayerState.PAUSED,
}

HELP = "↑↓ move  ⏎ select  ⌫ back  space play/pause  n/p next/prev  ,/. rew/ff  s shuffle  r repeat  q quit"

PAGE = 32
"""Records retrieved per request while browsing"""


@dataclass
class Level:
    """A list shown by the browser"""

    title: str
    category: DBCategory | None
    """Category of the records, None for the root list"""
    count: int
    names: dict[int, str] = field(default_factory=dict)
    cursor: int = 0
    top: int = 0


@dataclass
class NowPlaying:
    state: PlayerState = PlayerState.STOPPED
    index: int = -1
    total: int = 0
    title: str = ""
    artist: str = ""
    album: str = ""
    length_ms: int = 0
    position_ms: int = 0
    position_time: float = 0.0
    """When position_ms was reported, to advance it while playing"""
    shuffle: ShuffleMode = ShuffleMode.OFF
    repeat: RepeatMode = RepeatMode.OFF

    def position(self) -> int:
        position = self.position_ms
        if self.state == PlayerState.PLAYING:
            position += int((time.monotonic() - self.position_time) * 1000)
        return min(position, self.length_ms) if self.length_ms else position


def format_time(ms: int) -> str:
    seconds = ms // 1000
    return f"{seconds // 60}:{seconds % 60:02}"


class MessageHandler(logging.Handler):
    """Shows log messages in the footer while curses owns the terminal"""

    def __init__(self, tui: "TUI") -> None:
        super().__init__(logging.WARNING)
        self.tui = tui

    def emit(self, record: logging.LogRecord) -> None:
        self.tui.show_message(record.getMessage())


class TUI:
    def __init__(self, screen, iap: iAPClient, ei: ExtendedInterface) -> None:
        self.screen = screen
        self.iap = iap
        self.ei = ei

        self.lock = threading.Lock()
        self.now = NowPlaying()
        self.message = ""
        self.seeking: PlayControlCommand | None = None

        self.levels = [Level("Music", None, len(ROOT), {i: name for i, (name, _) in enumerate(ROOT)})]

    # --- iPod state -----------------------------------------------------------

    def show_message(self, message: str) -> None:
        self.message = message

    def refresh_now_playing(self) -> None:
        """Read the whole playback state, runs on the event thread"""

        try:
            status = self.ei.get_play_status()
            index = self.ei.get_current_playing_track_index()
            total = self.ei.get_num_playing_tracks()
            shuffle = self.ei.get_shuffle()
            repeat = self.ei.get_repeat()
        except iAPError as e:
            self.show_message(f"Reading play status failed: {e}")
            return

        with self.lock:
            self.now.state = status.state
            self.now.length_ms = status.length_ms
            self.now.position_ms = status.position_ms
            self.now.position_time = time.monotonic()
            self.now.total = total
            self.now.shuffle = shuffle
            self.now.repeat = repeat

        self.load_track(index)

    def load_track(self, index: int) -> None:
        """Read the playing track's names and length, runs on the event thread"""

        title = artist = album = ""
        length = 0

        try:
            if index >= 0:
                title = self.ei.get_indexed_playing_track_title(index)
                artist = self.ei.get_indexed_playing_track_artist_name(index)
                album = self.ei.get_indexed_playing_track_album_name(index)
                length = self.ei.get_play_status().length_ms
        except iAPError as e:
            self.show_message(f"Reading track info failed: {e}")

        with self.lock:
            self.now.index = index
            self.now.title, self.now.artist, self.now.album = title, artist, album
            self.now.length_ms = length

    def on_play_status(self, change: PlayStatusChange, value) -> None:
        """Play status notification listener, runs on the event thread"""

        with self.lock:
            now = self.now

            if change == PlayStatusChange.TRACK_INDEX:
                now.position_ms, now.position_time = 0, time.monotonic()
            elif change in (PlayStatusChange.TRACK_TIME_S, PlayStatusChange.TRACK_TIME_MS):
                scale = 1000 if change == PlayStatusChange.TRACK_TIME_S else 1
                now.position_ms, now.position_time = value * scale, time.monotonic()
            elif change == PlayStatusChange.PLAYBACK_STATUS_EXTENDED:
                if value in EXTENDED_STATES:
                    now.position_ms, now.position_time = now.position(), time.monotonic()
                    now.state = EXTENDED_STATES[value]
            elif change == PlayStatusChange.PLAYBACK_STOPPED:
                now.state = PlayerState.STOPPED
            elif change == PlayStatusChange.PLAYBACK_ENGINE_CONTENTS:
                now.total = value

        if change == PlayStatusChange.TRACK_INDEX:
            self.load_track(value)

    def start(self) -> None:
        self.ei.add_event_listener(None, self.on_play_status)

        events = [
            PlayStatusEvent.BASIC_PLAY_STATE,
            PlayStatusEvent.EXTENDED_PLAY_STATE,
            PlayStatusEvent.TRACK_INDEX,
            PlayStatusEvent.TRACK_TIME_S,
            PlayStatusEvent.PLAYBACK_ENGINE_CONTENTS,
        ]
        self.ei.set_play_status_change_notification(events)

        # The notifications only report changes
        self.iap.dispatch(self.refresh_now_playing)

    # --- browser --------------------------------------------------------------

    @property
    def level(self) -> Level:
        return self.levels[-1]

    def list_height(self) -> int:
        return max(1, self.screen.getmaxyx()[0] - 6)

    def load_visible(self) -> None:
        """Retrieve the names of the visible records that aren't cached yet"""

        level = self.level
        if level.category is None:
            return

        end = min(level.count, level.top + self.list_height())
        missing = [i for i in range(level.top, end) if i not in level.names]
        if not missing:
            return

        start = missing[0]
        count = min(max(PAGE, missing[-1] - start + 1), level.count - start)

        for index, name in self.ei.retrieve_categorized_database_records(
            level.category, start, count
        ):
            level.names[index] = name

        # Don't retry records the iPod didn't return
        for index in range(start, start + count):
            level.names.setdefault(index, "")

    def enter(self) -> None:
        level = self.level
        if level.count == 0:
            return

        index = level.cursor
        name = level.names.get(index, "")

        if level.category is None:
            category = ROOT[index][1]
            self.ei.reset_db_selection()
            count = self.ei.get_number_categorized_db_records(category)
            self.levels.append(Level(name, category, count))
            return

        self.ei.select_db_record(level.category, index)

        category = NEXT_CATEGORY.get(level.category)
        if category is None:
            # Selecting a single track passes it to the Playback Engine
            self.show_message(f"Playing {name}")
            return

        count = self.ei.get_number_categorized_db_records(category)
        self.levels.append(Level(name, category, count))

    def back(self) -> None:
        if len(self.levels) == 1:
            return

        self.levels.pop()
        parent = self.level

        if parent.category is not None:
            # Undo the parent's selection, and initialize its count again
            self.ei.select_db_record(parent.category, -1)
            parent.count = self.ei.get_number_categorized_db_records(parent.category)

    def move(self, delta: int) -> None:
        level = self.level
        level.cursor = max(0, min(level.count - 1, level.cursor + delta))

        height = self.list_height()
        if level.cursor < level.top:
            level.top = level.cursor
        elif level.cursor >= level.top + height:
            level.top = level.cursor - height + 1

    # --- playback controls ----------------------------------------------------

    def seek(self, command: PlayControlCommand) -> None:
        """Start seeking, or stop when already seeking"""

        if self.seeking is None:
            self.ei.play_control(command)
            self.seeking = command
        else:
            self.end_seek()

    def end_seek(self) -> None:
        if self.seeking is not None:
            self.seeking = None
            self.ei.play_control(PlayControlCommand.END_FF_REW)

    def cycle_shuffle(self) -> None:
        mode = ShuffleMode((self.now.shuffle + 1) % len(ShuffleMode))
        self.ei.set_shuffle(mode)
        with self.lock:
            self.now.shuffle = mode

    def cycle_repeat(self) -> None:
        mode = RepeatMode((self.now.repeat + 1) % len(RepeatMode))
        self.ei.set_repeat(mode)
        with self.lock:
            self.now.repeat = mode

    def handle_key(self, key: int) -> bool:
        """Handle a key press, returns False to quit"""

        if key in (ord(","), ord(".")):
            self.seek(
                PlayControlCommand.START_REW if key == ord(",") else PlayControlCommand.START_FF
            )
            return True

        # Any other key ends seeking, other play control commands are refused while seeking
        self.end_seek()

        if key in (ord("q"), ord("Q")):
            return False
        elif key in (curses.KEY_UP, ord("k")):
            self.move(-1)
        elif key in (curses.KEY_DOWN, ord("j")):
            self.move(1)
        elif key == curses.KEY_PPAGE:
            self.move(-self.list_height())
        elif key == curses.KEY_NPAGE:
            self.move(self.list_height())
        elif key == curses.KEY_HOME:
            self.move(-self.level.count)
        elif key == curses.KEY_END:
            self.move(self.level.count)
        elif key in (curses.KEY_ENTER, 10, 13, curses.KEY_RIGHT, ord("l")):
            self.enter()
        elif key in (curses.KEY_BACKSPACE, 127, 8, curses.KEY_LEFT, ord("h")):
            self.back()
        elif key == ord(" "):
            self.ei.play_control(PlayControlCommand.TOGGLE_PLAY_PAUSE)
        elif key == ord("n"):
            self.ei.play_control(PlayControlCommand.NEXT)
        elif key == ord("p"):
            self.ei.play_control(PlayControlCommand.PREVIOUS)
        elif key == ord("s"):
            self.cycle_shuffle()
        elif key == ord("r"):
            self.cycle_repeat()

        return True

    # --- drawing --------------------------------------------------------------

    def text(self, y: int, x: int, text: str, attr: int = 0) -> None:
        height, width = self.screen.getmaxyx()
        if 0 <= y < height and x < width:
            try:
                self.screen.addnstr(y, x, text, width - x - 1, attr)
            except curses.error:
                pass

    def draw(self) -> None:
        screen = self.screen
        screen.erase()
        height, width = screen.getmaxyx()

        with self.lock:
            now = self.now
            position = now.position()

            self.text(0, 1, STATE_LABELS.get(now.state, "?"), curses.A_DIM)
            self.text(0, 13, now.title or "Not playing", curses.A_BOLD)
            self.text(1, 13, " — ".join(n for n in (now.artist, now.album) if n))

            times = f"{format_time(position)} / {format_time(now.length_ms)}"
            bar_width = max(10, width - len(times) - 50)
            filled = bar_width * position // now.length_ms if now.length_ms else 0
            track = f"{now.index + 1}/{now.total}" if now.index >= 0 else f"-/{now.total}"

            self.text(2, 1, "━" * filled, curses.A_BOLD)
            self.text(2, 1 + filled, "─" * (bar_width - filled), curses.A_DIM)
            self.text(
                2,
                bar_width + 2,
                f"{times}  Track {track}  Shuffle: {now.shuffle.name.lower()}"
                f"  Repeat: {now.repeat.name.lower()}",
            )

        path = " › ".join(level.title for level in self.levels)
        self.text(3, 0, f" {path} ({self.level.count}) ".ljust(width), curses.A_REVERSE)

        level = self.level
        for row in range(self.list_height()):
            index = level.top + row
            if index >= level.count:
                break

            name = level.names.get(index, "…") or "(unknown)"
            attr = curses.A_REVERSE if index == level.cursor else 0
            self.text(4 + row, 0, f" {name}".ljust(width), attr)

        if self.seeking is not None:
            footer = "Seeking, press any key to stop"
        else:
            footer = self.message or HELP
        self.text(height - 1, 0, f" {footer}".ljust(width), curses.A_DIM)

        screen.refresh()

    def run(self) -> None:
        curses.curs_set(0)
        self.screen.keypad(True)
        self.screen.timeout(200)

        self.start()

        while self.iap.is_open:
            try:
                self.load_visible()
            except iAPError as e:
                self.show_message(f"Loading records failed: {e}")

            self.draw()

            key = self.screen.getch()
            if key == -1 or key == curses.KEY_RESIZE:
                continue

            self.message = ""
            try:
                if not self.handle_key(key):
                    break
            except iAPError as e:
                self.show_message(str(e))

        self.end_seek()


def extended_interface():
    parser = argparse.ArgumentParser(
        description="Browse and control the iPod in Extended Interface mode"
    )
    add_transport_args(parser)
    args = parser.parse_args()

    with iAPClient(make_transport(args), auth=make_auth(args)) as iap:
        ei = iap.register(ExtendedInterface)
        iap.start_identify()
        ei.enter_extended_mode()

        # The root logger, and the library's own when -v or --debug is given
        loggers = [logging.getLogger(), logging.getLogger("pypodcontrol")]
        handlers = [logger.handlers[:] for logger in loggers]

        def run(screen) -> None:
            tui = TUI(screen, iap, ei)

            # Log messages would garble the screen, show them in the footer
            for logger in loggers:
                logger.handlers = [MessageHandler(tui)]
            tui.run()

        try:
            curses.wrapper(run)
        except KeyboardInterrupt:
            pass
        finally:
            for logger, saved in zip(loggers, handlers):
                logger.handlers = saved

            if iap.is_open:
                try:
                    ei.exit_extended_mode()
                except iAPError as e:
                    print("Leaving Extended Interface mode failed:", e)


if __name__ == "__main__":
    extended_interface()
