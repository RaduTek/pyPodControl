import logging
import os
import sys

from ..errors import TransportError

logger = logging.getLogger(__name__)

APPLE_VENDOR_ID = 0x05AC

HID_INTERFACE_CLASS = 0x03


def is_apple_mobile_device(product_id: int) -> bool:
    """Whether an Apple product ID belongs to an iPod, iPhone or iPad"""

    return 0x1200 <= product_id <= 0x12FF


def _import_pyusb():
    try:
        import usb.core
        import usb.util
    except ImportError:
        raise TransportError(
            "Selecting the USB configuration requires pyusb: pip install pyPodControl[usb]"
        ) from None

    return usb.core, usb.util


def find_iui_configuration(device) -> int | None:
    """
    Find the iPod USB Interface (iUI) configuration of a pyusb device

    The iUI configuration is the one with a HID interface, the other one is
    mass storage. Returns its bConfigurationValue, or None if there is none.
    """

    for config in device:
        if any(intf.bInterfaceClass == HID_INTERFACE_CLASS for intf in config):
            return config.bConfigurationValue

    return None


def _sysfs_path(device) -> str | None:
    """sysfs directory of a pyusb device (Linux only)"""

    ports = getattr(device, "port_numbers", None)
    if not ports:
        return None

    path = f"/sys/bus/usb/devices/{device.bus}-{'.'.join(map(str, ports))}"
    return os.path.realpath(path) if os.path.exists(path) else None


def _block_devices(sysfs_path: str) -> set[str]:
    """Names of block devices (disks and partitions) below a sysfs directory"""

    names = set()

    for root, dirs, _ in os.walk(sysfs_path):
        if os.path.basename(root) != "block":
            continue

        for disk in dirs:
            names.add(disk)
            disk_path = os.path.join(root, disk)
            for part in os.listdir(disk_path):
                if os.path.exists(os.path.join(disk_path, part, "partition")):
                    names.add(part)

    return names


def is_mounted(device) -> bool:
    """
    Whether the device's mass storage is mounted

    Best effort, only supported on Linux, returns False elsewhere
    """

    if not sys.platform.startswith("linux"):
        return False

    sysfs_path = _sysfs_path(device)
    if sysfs_path is None:
        return False

    names = _block_devices(sysfs_path)
    if not names:
        return False

    try:
        with open("/proc/mounts") as mounts:
            for line in mounts:
                source = line.split(" ", 1)[0]
                if os.path.basename(os.path.realpath(source)) in names:
                    return True
    except OSError:
        return False

    return False


def _active_configuration(device) -> int | None:
    try:
        return device.get_active_configuration().bConfigurationValue
    except Exception:
        # Unconfigured device
        return None


def _detach_kernel_drivers(device, config_value: int | None) -> None:
    """Detach kernel drivers (e.g. usb-storage) from the active configuration"""

    if config_value is None:
        return

    numbers = {intf.bInterfaceNumber for intf in device.get_active_configuration()}

    for number in sorted(numbers):
        try:
            if device.is_kernel_driver_active(number):
                logger.debug("Detaching kernel driver from interface %d", number)
                device.detach_kernel_driver(number)
        except NotImplementedError:
            # Not supported by this platform's backend
            return


def select_iui_configuration(
    vendor_id: int = APPLE_VENDOR_ID,
    product_id: int | None = None,
    *,
    check_mounted: bool = True,
) -> int:
    """
    Switch an iPod from mass storage to its iPod USB Interface configuration

    The iUI configuration provides iAP over HID and USB audio. Switching away
    from mass storage disconnects the iPod's disk, so this refuses to switch
    while it is mounted (on Linux), unless check_mounted is False.

    Requires pyusb and write access to the USB device (root, or a udev rule).

    Returns the product ID of the selected device.
    """

    core, util = _import_pyusb()

    def match(device) -> bool:
        if product_id is not None:
            return device.idProduct == product_id
        return is_apple_mobile_device(device.idProduct)

    try:
        devices = list(
            core.find(find_all=True, idVendor=vendor_id, custom_match=match)
        )
    except core.NoBackendError as e:
        raise TransportError(f"No libusb backend available for pyusb: {e}") from e

    # Every device whose descriptors are read opens a libusb handle; all of them
    # must be released before returning. A handle left open (with a detached
    # kernel driver) wedges the host USB stack when the iPod is unplugged, so
    # hidapi reopens the device fresh after the switch rather than reusing this.
    try:
        for device in devices:
            try:
                config_value = find_iui_configuration(device)
            except core.USBError as e:
                logger.debug("Skipping %04x:%04x: %s", vendor_id, device.idProduct, e)
                continue

            if config_value is None:
                continue

            current = _active_configuration(device)

            if current == config_value:
                logger.debug("iUI configuration %d already selected", config_value)
                return device.idProduct

            if check_mounted and is_mounted(device):
                raise TransportError(
                    "The iPod's disk is mounted, eject it before switching to the iPod USB Interface"
                )

            logger.info("Selecting iUI configuration %d", config_value)

            try:
                _detach_kernel_drivers(device, current)
                device.set_configuration(config_value)
            except core.USBError as e:
                raise TransportError(
                    f"Failed to select USB configuration {config_value}: {e} "
                    "(root or a udev rule granting access to the device is needed)"
                ) from e

            return device.idProduct

        raise TransportError("No iPod with an iPod USB Interface configuration found")
    finally:
        # libusb issues the SET_CONFIGURATION request on the wire, so closing the
        # handle here keeps the iPod in its new configuration
        for device in devices:
            try:
                util.dispose_resources(device)
            except Exception:
                logger.debug("Failed to release USB device", exc_info=True)
