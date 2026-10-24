import argparse
import logging

from pypodcontrol import iAPClient, iAPError
from pypodcontrol.lingo import General, SimpleRemote
from pypodcontrol.transport import UARTTransport, Transport


def make_transport(args) -> Transport:
    if args.usb:
        from pypodcontrol.transport import USBHIDTransport

        return USBHIDTransport()

    return UARTTransport(args.port, args.baudrate)


def info():
    parser = argparse.ArgumentParser(description="Print information about the iPod")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serial port")
    parser.add_argument("--baudrate", type=int, default=19200)
    parser.add_argument("--usb", action="store_true", help="Use USB HID transport")
    parser.add_argument("-v", "--verbose", action="store_true", help="Log packets")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    with iAPClient(make_transport(args)) as iap:
        iap.general.identify(SimpleRemote)

        try:
            print("Name:", iap.general.request_ipod_name())

            for lingo in (General, SimpleRemote):
                major, minor = iap.general.request_lingo_protocol_version(lingo)
                print(f"{lingo.__name__} lingo version: {major}.{minor:02}")
        except iAPError as e:
            print("Error:", e)


if __name__ == "__main__":
    info()
