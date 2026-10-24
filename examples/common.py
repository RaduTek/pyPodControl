import argparse
import logging

from pypodcontrol.auth import AuthenticationProvider, BypassedAuthenticationProvider
from pypodcontrol.transport import Transport, UARTTransport


def add_transport_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments for choosing the transport (UART or USB) to a parser"""

    group = parser.add_argument_group("transport")
    group.add_argument(
        "--usb", action="store_true", help="Use USB HID transport instead of UART"
    )
    group.add_argument(
        "--auth",
        action="store_true",
        help="Authenticate using the bypass provider (needs a patched iPod)",
    )
    group.add_argument(
        "--port", default="/dev/ttyUSB0", help="UART serial port (default: %(default)s)"
    )
    group.add_argument(
        "--baudrate",
        type=int,
        default=19200,
        help="UART baud rate (default: %(default)s)",
    )
    group.add_argument(
        "--no-select-configuration",
        dest="select_configuration",
        action="store_false",
        help="USB: don't switch the iPod from mass storage to iPod USB Interface mode",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Log packets")


def make_transport(args: argparse.Namespace) -> Transport:
    """Create the transport selected by the arguments"""

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    if args.usb:
        from pypodcontrol.transport import USBHIDTransport

        return USBHIDTransport(select_configuration=args.select_configuration)

    return UARTTransport(args.port, args.baudrate)


def make_auth(args: argparse.Namespace) -> AuthenticationProvider | None:
    """Create the authentication provider selected by the arguments"""

    return BypassedAuthenticationProvider() if args.auth else None
