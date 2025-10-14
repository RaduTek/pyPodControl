import sys
from pypodcontrol import iAPClient, General, SimpleRemote


def print_usage(msg: str = ""):
    if len(msg) > 0:
        print(msg)
    print(f"usage: python3 {sys.argv[0]} button [duration] [repeat]")
    print("Available buttons:", ", ".join(SimpleRemote.buttons))
    exit(1)


def simple_remote_test():
    if len(sys.argv) < 2:
        return print_usage("Missing button argument")

    button = sys.argv[1]

    duration = 0.1
    if len(sys.argv) >= 3:
        duration = float(sys.argv[2])

    repeat = 1

    if len(sys.argv) >= 4:
        repeat = int(sys.argv[3])

    if button not in SimpleRemote.buttons:
        return print_usage(f"Unknown button: {button}")

    iap = iAPClient("/dev/ttyUSB0")

    g = General(iap)

    g.identify(SimpleRemote)

    sr = SimpleRemote(iap)

    sr.press_button(button, duration, repeat)


if __name__ == "__main__":
    simple_remote_test()
