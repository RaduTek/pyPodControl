import sys
from pypodcontrol import iAPBase, SimpleRemote

iap = iAPBase("/dev/ttyUSB0")

sr = SimpleRemote(iap)

sr.press_button(sys.argv[1])
