import logging
import sys

from .lingo import General, Lingo
from .packet import Packet

TRAFFIC_LOGGER = "pypodcontrol.traffic"
"""Logger that logs every packet sent to and received from the iPod, at DEBUG level"""

traffic_logger = logging.getLogger(TRAFFIC_LOGGER)

LINGO_NAMES = {
    0x00: "General",
    0x01: "Microphone",
    0x02: "SimpleRemote",
    0x03: "DisplayRemote",
    0x04: "ExtendedInterface",
    0x05: "AccessoryPower",
    0x06: "USBHostMode",
    0x07: "RFTuner",
    0x08: "AccessoryEqualizer",
    0x09: "Sports",
    0x0A: "DigitalAudio",
    0x0C: "Storage",
    0x0D: "iPodOut",
    0x0E: "Location",
}
"""Names of the lingoes defined by iAP, for packets of unregistered lingoes"""

LOG_FORMAT = "%(asctime)s.%(msecs)03d %(threadName)s %(levelname)s %(name)s: %(message)s"


def enable_logging(level: int = logging.DEBUG, traffic: bool = True) -> None:
    """
    Print pyPodControl's log messages to stderr

    - level: Minimum level of the messages to print
    - traffic: Also print every packet sent and received (the pypodcontrol.traffic logger)

    With your own logging setup, enable the packet log with
    `logging.getLogger("pypodcontrol.traffic").setLevel(logging.DEBUG)` instead.
    """

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%H:%M:%S"))

    library_logger = logging.getLogger("pypodcontrol")
    library_logger.addHandler(handler)
    library_logger.setLevel(level)
    library_logger.propagate = False

    traffic_logger.setLevel(logging.DEBUG if traffic else logging.WARNING)


def ack_status_name(status: int) -> str:
    """Description of an ACK status code"""

    return General.ACK_STATUSES.get(status, f"Unknown status 0x{status:02X}")


def describe_packet(lingo: Lingo | None, packet: Packet) -> str:
    """Describe a packet as Lingo.Command, with its transaction ID, decoded ACK and data"""

    if lingo is not None:
        name = f"{type(lingo).__name__}.{lingo.command_name(packet.command_id)}"
    else:
        lingo_name = LINGO_NAMES.get(packet.lingo_id, f"Lingo(0x{packet.lingo_id:02X})")
        name = f"{lingo_name}.Unknown(0x{packet.command_id:02X})"

    parts = [name]

    if packet.transaction_id is not None:
        parts.append(f"#{packet.transaction_id}")

    ack = lingo.parse_ack(packet) if lingo is not None else None
    if ack is not None:
        status, command_id = ack
        parts.append(f"({ack_status_name(status)}: {lingo.command_name(command_id)})")

    if len(packet.data) > 16:
        parts.append(f"[{len(packet.data)} bytes]")

    if packet.data:
        parts.append(packet.data.hex(" "))

    return " ".join(parts)


def log_packet(direction: str, lingo: Lingo | None, packet: Packet) -> None:
    """Log a packet to the traffic logger, direction is "->" (sent) or "<-" (received)"""

    if traffic_logger.isEnabledFor(logging.DEBUG):
        traffic_logger.debug("%s %s", direction, describe_packet(lingo, packet))
