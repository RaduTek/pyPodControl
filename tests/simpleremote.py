import sys
from pypodcontrol import iAPClient, General, SimpleRemote

if len(sys.argv) < 2:
    print("Missing button argument")
    print("Available buttons", SimpleRemote.buttons)
    exit(1)

button = sys.argv[1]

if button not in SimpleRemote.buttons:
    print("Unknown button:", button)
    print("Available buttons", SimpleRemote.buttons)
    exit(1)

iap = iAPClient("/dev/ttyUSB0")

g = General(iap)

g.identify(SimpleRemote)

sr = SimpleRemote(iap)

sr.press_button(sys.argv[1])
