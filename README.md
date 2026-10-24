# pyPodControl

Implementation of Apple iPod Accessory Protocol (iAP) over UART and USB in Python

## How-To

Connect the iPod (or iPhone, or iPad) with a 30 pin docking connector via a breakout cable to a USB->UART adapter, or to a UART port on your SBC (not tested yet).

A 500k resistor on pin 21 may be needed. (In my testing it's been working without one)

**Important**: iPod uses TTL 3.3V serial

## Usage

```python
from pypodcontrol import iAPClient
from pypodcontrol.transport import UARTTransport
from pypodcontrol.lingo import SimpleRemote

with iAPClient(UARTTransport("/dev/ttyUSB0")) as iap:
    sr = iap.register(SimpleRemote())
    iap.general.identify(sr)

    print(iap.general.request_ipod_name())
    sr.press_button("play_pause")
```

-   `iAPClient` joins a transport with the registered lingos. The General lingo is always registered and available as `iap.general`. Other lingos are registered with `iap.register()`.
-   Commands that expect a response block until the response arrives, raising `iAPTimeoutError` if none arrives in time, or `iAPAckError` if the iPod returns an error status.
-   Unsolicited packets from the iPod can be handled with `lingo.add_listener(command, callback)`. Callbacks run on the transport's reader thread.
-   Pass `use_idps=True` together with an `AuthenticationProvider` (`auth=...`) to identify using IDPS. This enables transaction IDs.

### Transports

-   `UARTTransport(port, baudrate=19200)`: serial UART on the 30 pin connector
-   `USBHIDTransport()`: USB, with the computer as host and the iPod in its iPod USB Interface (iUI) configuration. Requires `pip install pyPodControl[usb]`

See the `examples/` directory for complete scripts.

## Development

```sh
pip install -e .[dev]
pytest
```

## Resources

-   [Official iPod Accessory Protocol Specification (archive.org)](https://archive.org/details/ipod-accessory-protocol-interface-specification/)
