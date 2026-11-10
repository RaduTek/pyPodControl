from .base import Transport
from .uart import UARTTransport
from .usbconfig import select_iui_configuration


def __getattr__(name: str):
    # USB HID transport needs the optional hidapi dependency
    if name == "USBHIDTransport":
        from .usbhid import USBHIDTransport

        return USBHIDTransport

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
