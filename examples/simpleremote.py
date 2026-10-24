import argparse

from common import add_transport_args, make_auth, make_transport
from pypodcontrol import iAPClient
from pypodcontrol.lingo import SimpleRemote


def simple_remote_test():
    parser = argparse.ArgumentParser(description="Press a button on the iPod")
    parser.add_argument(
        "button",
        choices=SimpleRemote.buttons,
        metavar="button",
        help="Button to press: " + ", ".join(SimpleRemote.buttons),
    )
    parser.add_argument(
        "duration",
        type=float,
        nargs="?",
        default=0.1,
        help="Time to hold the button, in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "repeat",
        type=int,
        nargs="?",
        default=1,
        help="Number of button presses (default: %(default)s)",
    )
    add_transport_args(parser)
    args = parser.parse_args()

    with iAPClient(make_transport(args), auth=make_auth(args)) as iap:
        sr = iap.register(SimpleRemote())

        iap.start_identify()

        sr.press_button(args.button, args.duration, args.repeat)


if __name__ == "__main__":
    simple_remote_test()
