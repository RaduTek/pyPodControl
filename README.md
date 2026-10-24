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
    iap.start_identify()

    print(iap.general.request_ipod_name())
    sr.press_button("play_pause")
```

-   `iAPClient` joins a transport with the registered lingos. The General lingo is always registered and available as `iap.general`. Other lingos are registered with `iap.register()`.
-   Commands that expect a response block until the response arrives, raising `iAPTimeoutError` if none arrives in time, or `iAPAckError` if the iPod returns an error status.
-   Unsolicited packets from the iPod can be handled with `lingo.add_listener(command, callback)`. Callbacks run on the transport's reader thread.
-   `iap.start_identify(authenticate, power_options)` identifies the accessory and all registered lingoes to the iPod. It uses `IdentifyDeviceLingoes` by default.
    -   `authenticate=True` requests immediate authentication, and needs an `AuthenticationProvider` (`auth=...`).
    -   `power_options` declares how much power the accessory draws from the iPod (`PowerOption.LOW_POWER`, `INTERMITTENT_HIGH_POWER` or `CONSTANT_HIGH_POWER`).
-   Pass `use_idps=True` together with an `AuthenticationProvider` to identify using IDPS instead. This enables transaction IDs and sends the accessory information given as `accessory_info=AccessoryInfo(...)`. iPods that don't support IDPS fall back to `IdentifyDeviceLingoes`.

### Authentication

Authenticated lingoes and commands require Made-for-iPod authentication, which normally needs an Apple authentication coprocessor. iPods running firmware that bypasses the signature check (such as [RepriseOS](https://github.com/RaduTek/repriseos-lab) on the iPod Classic) accept any signature, so `BypassedAuthenticationProvider` can authenticate without a coprocessor:

```python
from pypodcontrol import iAPClient
from pypodcontrol.auth import BypassedAuthenticationProvider
from pypodcontrol.transport import UARTTransport

auth = BypassedAuthenticationProvider()  # device_id defaults to 0x200
with iAPClient(UARTTransport("/dev/ttyUSB0"), auth=auth) as iap:
    iap.start_identify()  # authenticates because a provider is set
```

The iPod still performs a genuine certificate check, so a real Apple X.509 certificate is required. One captured from a successful authentication ships with the library (`pypodcontrol/auth/apple_auth_cert.bin`) and is used by default; pass a different path to the constructor to override it. This only works on a patched iPod; a stock iPod rejects the mock signature.

The examples authenticate this way by default; pass `--no-auth` to identify without authenticating (for a stock iPod).

### Transports

-   `UARTTransport(port, baudrate=19200)`: serial UART on the 30 pin connector
-   `USBHIDTransport()`: USB, with the computer as host and the iPod in its iPod USB Interface (iUI) configuration. Requires `pip install pyPodControl[usb]`

#### Switching the iPod to iAP mode over USB

When an iPod is plugged in over USB, it starts in its mass storage configuration. iAP over HID (together with USB audio) is only available in its second configuration, the "iPod USB Interface". Pass `select_configuration=True` to switch to it when the transport opens:

```python
transport = USBHIDTransport(select_configuration=True)
```

This uses pyusb, and it refuses to switch while the iPod's disk is mounted, since switching disconnects the disk. Eject the iPod first. `select_iui_configuration()` in `pypodcontrol.transport` does the same switch on its own.

On Linux, the user running the code needs access to the iPod's USB device and its hidraw node, for example with a udev rule in `/etc/udev/rules.d/70-ipod.rules`:

```
SUBSYSTEM=="usb", ATTR{idVendor}=="05ac", ATTR{idProduct}=="12??", MODE="0660", TAG+="uaccess"
KERNEL=="hidraw*", ATTRS{idVendor}=="05ac", ATTRS{idProduct}=="12??", MODE="0660", TAG+="uaccess"
```

Alternatively, udev can always switch iPods to the iUI configuration as soon as they are connected. This makes their disks unavailable:

```
SUBSYSTEM=="usb", ATTR{idVendor}=="05ac", ATTR{idProduct}=="12??", ATTR{bConfigurationValue}="2"
```

See the `examples/` directory for complete scripts.

## Development

```sh
pip install -e .[dev]
pytest
```

## Resources

-   [Official iPod Accessory Protocol Specification (archive.org)](https://archive.org/details/ipod-accessory-protocol-interface-specification/)
