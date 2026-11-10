import argparse
import logging

from pypodcontrol import enable_logging
from pypodcontrol.auth import AuthenticationProvider, BypassedAuthenticationProvider
from pypodcontrol.transport import Transport, UARTTransport

# Under pypodcontrol, so enable_logging() shows it too
logger = logging.getLogger("pypodcontrol.examples")


def add_transport_args(parser: argparse.ArgumentParser) -> None:
    """Add arguments for choosing the transport (UART or USB) to a parser"""

    group = parser.add_argument_group("transport")
    group.add_argument(
        "--usb", action="store_true", help="Use USB HID transport instead of UART"
    )
    group.add_argument(
        "--no-auth",
        dest="auth",
        action="store_false",
        help="Skip authentication (identify only; use for a stock iPod)",
    )
    group.add_argument(
        "--i2c-bus",
        type=int,
        default=None,
        help="Authenticate with an Apple coprocessor on this I2C bus number "
        "(default: bypass provider)",
    )
    group.add_argument(
        "--i2c-address",
        type=lambda v: int(v, 0),
        default=0x10,
        help="Coprocessor 7-bit I2C address, 0x10 or 0x11 (default: 0x10)",
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
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Log what the library is doing"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Log debug messages, including every packet sent and received",
    )


def make_transport(args: argparse.Namespace) -> Transport:
    """Create the transport selected by the arguments"""

    if args.debug:
        enable_logging(logging.DEBUG, traffic=True)
    elif args.verbose:
        enable_logging(logging.INFO, traffic=False)
    else:
        logging.basicConfig(level=logging.WARNING)

    if args.usb:
        from pypodcontrol.transport import USBHIDTransport

        return USBHIDTransport(select_configuration=args.select_configuration)

    return UARTTransport(args.port, args.baudrate)


def make_auth(args: argparse.Namespace) -> AuthenticationProvider | None:
    """Create the authentication provider selected by the arguments"""

    if not args.auth:
        return None

    if args.i2c_bus is not None:
        from pypodcontrol.auth import CoprocessorAuthenticationProvider

        logger.info("Authenticating with the I2C coprocessor")
        return CoprocessorAuthenticationProvider(args.i2c_bus, args.i2c_address)

    logger.info("Authenticating with the bypass provider (needs a patched iPod)")
    return BypassedAuthenticationProvider()
