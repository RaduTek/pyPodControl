import sys
from pypodcontrol import iAPClient
from pypodcontrol.lingo import General, SimpleRemote

iap = iAPClient("/dev/ttyUSB0")

g = General(iap)

g.identify(0x04)
