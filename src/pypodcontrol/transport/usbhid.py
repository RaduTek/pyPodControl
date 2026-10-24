from ..errors import TransportError
from .base import Transport

try:
    import hid
except ImportError:  # pragma: no cover - depends on optional dependency
    hid = None

APPLE_VENDOR_ID = 0x05AC

LCB_CONTINUATION = 0x01
"""Link control byte: report continues a set started by a previous report"""

LCB_MORE_TO_FOLLOW = 0x02
"""Link control byte: more reports follow in this set"""


def parse_report_descriptor(
    descriptor: bytes,
) -> tuple[dict[int, int], dict[int, int]]:
    """
    Parse the input and output report sizes from a HID report descriptor

    Returns (input reports, output reports), each mapping report ID to the
    report payload size in bytes (excluding the report ID byte)
    """

    inputs: dict[int, int] = {}
    outputs: dict[int, int] = {}

    report_id = 0
    report_size = 0
    report_count = 0
    stack: list[tuple[int, int, int]] = []

    i = 0
    while i < len(descriptor):
        prefix = descriptor[i]

        # Long item: 0xFE, data size, long item tag, data
        if prefix == 0xFE:
            if i + 1 >= len(descriptor):
                break
            i += 3 + descriptor[i + 1]
            continue

        size = (0, 1, 2, 4)[prefix & 0x03]
        item_type = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F
        value = int.from_bytes(descriptor[i + 1 : i + 1 + size], "little")
        i += 1 + size

        if item_type == 0:  # Main
            if tag in (0x8, 0x9):  # Input, Output
                reports = inputs if tag == 0x8 else outputs
                reports[report_id] = reports.get(report_id, 0) + report_size * report_count
        elif item_type == 1:  # Global
            if tag == 0x7:
                report_size = value
            elif tag == 0x8:
                report_id = value
            elif tag == 0x9:
                report_count = value
            elif tag == 0xA:
                stack.append((report_id, report_size, report_count))
            elif tag == 0xB and stack:
                report_id, report_size, report_count = stack.pop()

    def to_bytes(reports: dict[int, int]) -> dict[int, int]:
        return {rid: (bits + 7) // 8 for rid, bits in reports.items() if bits > 0}

    return to_bytes(inputs), to_bytes(outputs)


def pack_reports(frame: bytes, output_reports: dict[int, int]) -> list[bytes]:
    """
    Split a packet frame across HID output reports

    Each report is the report ID, a link control byte, and frame data padded with zeros
    """

    if not output_reports:
        raise TransportError("No HID output reports available")

    # Report payload sizes include the link control byte
    by_size = sorted(output_reports.items(), key=lambda r: (r[1], r[0]))
    largest = by_size[-1]

    reports = []
    offset = 0

    while offset < len(frame):
        remaining = len(frame) - offset

        report_id, size = next(
            (r for r in by_size if r[1] - 1 >= remaining), largest
        )

        chunk = frame[offset : offset + size - 1]
        offset += len(chunk)

        lcb = LCB_CONTINUATION if reports else 0x00
        if offset < len(frame):
            lcb |= LCB_MORE_TO_FOLLOW

        reports.append(
            bytes([report_id, lcb]) + chunk + bytes(size - 1 - len(chunk))
        )

    return reports


class USBHIDTransport(Transport):
    """
    ### USBHIDTransport

    iAP over USB HID, with the computer as USB host and the iPod as device

    The iPod must be in its iPod USB Interface (iUI) configuration. Requires
    the optional `hidapi` dependency (`pip install pyPodControl[usb]`).
    """

    read_timeout_ms: int = 100
    """Read timeout of the reader thread, in milliseconds"""

    input_reports: dict[int, int]
    """Input report sizes by report ID, parsed on open"""

    output_reports: dict[int, int]
    """Output report sizes by report ID, parsed on open"""

    def __init__(
        self,
        vendor_id: int = APPLE_VENDOR_ID,
        product_id: int | None = None,
        path: bytes | None = None,
    ) -> None:
        """
        Create a new USB HID transport

        - vendor_id: USB vendor ID, Apple by default
        - product_id: USB product ID, or None for the first matching device
        - path: hidapi device path, overrides vendor_id and product_id
        """

        if hid is None:
            raise TransportError(
                "USB HID transport requires hidapi: pip install pyPodControl[usb]"
            )

        super().__init__()

        self.vendor_id = vendor_id
        self.product_id = product_id
        self.path = path
        self.device = None
        self.input_reports = {}
        self.output_reports = {}

    def _find_path(self) -> bytes:
        devices = hid.enumerate(self.vendor_id, self.product_id or 0)

        if not devices:
            raise TransportError(
                f"No HID device found for {self.vendor_id:04x}:{self.product_id or 0:04x}"
            )

        return devices[0]["path"]

    def _open(self) -> None:
        path = self.path or self._find_path()

        device = hid.device()
        try:
            device.open_path(path)
        except (IOError, OSError) as e:
            raise TransportError(f"Failed to open HID device {path!r}: {e}") from e

        try:
            # The report layout may change between devices, parse it on every open
            descriptor = bytes(device.get_report_descriptor())
        except AttributeError:
            device.close()
            raise TransportError("hidapi >= 0.14 is required to read report descriptors")
        except (IOError, OSError) as e:
            device.close()
            raise TransportError(f"Failed to read HID report descriptor: {e}") from e

        self.input_reports, self.output_reports = parse_report_descriptor(descriptor)

        if not self.input_reports or not self.output_reports:
            device.close()
            raise TransportError("HID device has no iAP input/output reports")

        self.device = device

    def _close(self) -> None:
        if self.device is not None:
            self.device.close()
            self.device = None

    def _read_chunk(self) -> bytes:
        size = max(self.input_reports.values()) + 1
        report = bytes(self.device.read(size, timeout_ms=self.read_timeout_ms))

        if len(report) < 2:
            return b""

        lcb = report[1]

        # A report that does not continue a set flushes incomplete packets
        if not lcb & LCB_CONTINUATION and self.parser.in_packet:
            self.parser.reset()

        return report[2:]

    def _write_frame(self, frame: bytes) -> None:
        for report in pack_reports(frame, self.output_reports):
            try:
                written = self.device.write(report)
            except (IOError, OSError) as e:
                raise TransportError(f"Failed to write HID report: {e}") from e

            if written < 0:
                raise TransportError("Failed to write HID report")
