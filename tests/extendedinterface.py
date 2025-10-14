import sys
from pypodcontrol import iAPClient, General, SimpleRemote

iap = iAPClient("/dev/ttyUSB0")

g = General(iap)

g.identify(0x04)
