import sys
import tty
from pypodcontrol import iAPClient
from pypodcontrol.lingo import General, SimpleRemote

keymap = {
    "z": "stop",
    "x": "pause",
    "c": "play",
    "v": "shuffle",
    "b": "repeat",
    "n": "previous_track",
    "m": "next_track",
    "N": "previous_album",
    "M": "next_album",
    " ": "play_pause",
    ",": "volume_down",
    ".": "volume_up",
    "/": "mute",
    "w": "up",
    "a": "menu",
    "s": "down",
    "d": "select",
    "j": "previous_playlist",
    "k": "next_playlist",
    "J": "previous_chapter",
    "K": "next_chapter",
    "1": "power_on",
    "2": "power_off",
    "3": "backlight",
    "4": "backlight_off",
}


def print_help():
    print("Available commands:")
    for key, command in keymap.items():
        print(f"\t{key}: {command}")


def keyboard_remote():
    iap = iAPClient("/dev/ttyUSB0")

    g = General(iap)

    g.identify(SimpleRemote)

    sr = SimpleRemote(iap)

    tty.setcbreak(sys.stdin.fileno())

    print("Press a key (h for help, q to quit)...", end="\r", flush=True)

    while True:
        key = sys.stdin.read(1)

        if key == "h":
            print_help()
            continue

        if key == "q":
            break

        if not key in keymap.keys():
            continue

        button = keymap[key]

        print("Press:", button, " " * 6, end="\r", flush=True)
        sr.press_button(button)

    print("\nBye, bye!")


if __name__ == "__main__":
    keyboard_remote()
