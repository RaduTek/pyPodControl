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
-   Unsolicited packets from the iPod can be handled with `lingo.add_listener(command, callback)`. Callbacks run on the client's event thread, see [Event driven scripts](#event-driven-scripts).
-   `iap.start_identify(authenticate, power_options)` identifies the accessory and all registered lingoes to the iPod. It uses `IdentifyDeviceLingoes` by default.
    -   `authenticate=True` requests immediate authentication, and needs an `AuthenticationProvider` (`auth=...`).
    -   `power_options` declares how much power the accessory draws from the iPod (`PowerOption.LOW_POWER`, `INTERMITTENT_HIGH_POWER` or `CONSTANT_HIGH_POWER`).
-   Pass `use_idps=True` together with an `AuthenticationProvider` to identify using IDPS instead. This enables transaction IDs and sends the accessory information given as `accessory_info=AccessoryInfo(...)`. iPods that don't support IDPS fall back to `IdentifyDeviceLingoes`.

### Event driven scripts

A script can set up listeners, enable the iPod's notifications and then wait for events. For example, with the Display Remote lingo:

```python
from pypodcontrol import iAPClient
from pypodcontrol.lingo import DisplayRemote, RemoteEvent, TrackInfoType

with iAPClient(transport, auth=auth) as iap:
    dr = iap.register(DisplayRemote)
    iap.start_identify()

    def on_track(event, index):
        print("Now playing:", dr.get_track_text(TrackInfoType.TITLE, index))

    def on_volume(event, volume):
        print("Volume:", "muted" if volume.muted else volume.ui_level)

    dr.add_event_listener(RemoteEvent.TRACK_INDEX, on_track)
    dr.add_event_listener(RemoteEvent.ABSOLUTE_VOLUME, on_volume)
    dr.set_remote_event_notification([RemoteEvent.TRACK_INDEX, RemoteEvent.ABSOLUTE_VOLUME])

    try:
        iap.wait_until_closed()  # until the iPod disconnects
    except KeyboardInterrupt:
        pass
```

-   `iap.wait_until_closed(timeout=None)` blocks until the client is closed or the iPod disconnects, and can be interrupted with Ctrl+C.
-   Listeners run on the client's event thread, one at a time, in the order the iPod sent the packets. They can send requests to the iPod (like `get_track_text` above), but a slow listener delays the events after it.
-   `iap.dispatch(callback)` runs any callback on the event thread, e.g. to serialize work with the listeners.

See `examples/displayremote.py` for a complete script.

### Extended Interface

The Extended Interface lingo browses the iPod's database and controls playback. The iPod has to be put in Extended Interface mode first, which shows an "OK to disconnect" screen and disables its buttons:

```python
from pypodcontrol import iAPClient
from pypodcontrol.lingo import DBCategory, ExtendedInterface, PlayStatusChange, PlayStatusEvent

with iAPClient(transport, auth=auth) as iap:
    ei = iap.register(ExtendedInterface)
    iap.start_identify()
    ei.enter_extended_mode()

    # Selections narrow each other: an artist, then one of their albums
    ei.reset_db_selection()
    ei.get_number_categorized_db_records(DBCategory.ARTIST)  # required before selecting
    print(ei.retrieve_categorized_database_records(DBCategory.ARTIST, 0, 10))
    ei.select_db_record(DBCategory.ARTIST, 0)

    ei.get_number_categorized_db_records(DBCategory.ALBUM)
    ei.select_db_record(DBCategory.ALBUM, 0)

    # Selecting a single track starts playing it
    ei.get_number_categorized_db_records(DBCategory.TRACK)
    ei.select_db_record(DBCategory.TRACK, 0)

    def on_track(change, index):
        print("Now playing:", ei.get_indexed_playing_track_title(index))

    ei.add_event_listener(PlayStatusChange.TRACK_INDEX, on_track)
    ei.set_play_status_change_notification([PlayStatusEvent.TRACK_INDEX])
    ...
    ei.exit_extended_mode()
```

-   Commands answered with several packets (database records, `get_db_track_info()`, artwork) gather them until all are received, or until the iPod stops sending for `idle_timeout` seconds when their number isn't known up front.
-   Artwork is returned as an `Artwork` with the raw pixel data. With Pillow installed (`pip install pyPodControl[image]`), `artwork.to_image()` converts it to a `PIL.Image`, which other libraries can use: `pygame.image.frombytes(img.tobytes(), img.size, img.mode)` for pygame, or `PIL.ImageQt.ImageQt(img)` for Qt. `ei.set_display_image(img)` sends a Pillow image to the iPod's screen.

See `examples/extendedinterface.py` for a terminal UI that browses the library and controls playback (it needs `windows-curses` on Windows).

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

#### Linux: USB permissions

The user running the code needs access to the iPod's USB device node (`/dev/bus/usb/...`, used by hidapi's default libusb backend and by pyusb) and its hidraw node. Install the udev rules from `extras/linux/70-ipod.rules`:

```
sudo cp extras/linux/70-ipod.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

The rules grant access with `uaccess` to the user logged in at the computer, and to the `plugdev` group. `uaccess` only applies to a local desktop session, not to SSH or headless sessions such as on a Raspberry Pi, so there the user must be in `plugdev` (`sudo usermod -aG plugdev $USER`, then log in again). Raspberry Pi OS's default user already is.

#### Linux: always use the iUI configuration

The kernel configures a USB device as it enumerates it, before udev sees it, and picks the iPod's mass storage configuration. A udev rule that switches to the iUI configuration (commented out in `70-ipod.rules`) works, but the iPod is briefly put in mass storage mode first, which stops playback and shows its disk mode screen.

The `ipod-iui` kernel module in `extras/linux/ipod-iui` avoids this: it makes the kernel choose the iUI configuration in the first place. It needs Linux 6.8 or newer and the kernel headers (`raspberrypi-kernel-headers` on Raspberry Pi OS, `kernel-devel` on Fedora). It also conflicts with `apple-mfi-fastcharge`, which has to be blacklisted, see below.

```
cd extras/linux/ipod-iui
make
sudo make install
echo ipod_iui | sudo tee /etc/modules-load.d/ipod-iui.conf
sudo modprobe ipod_iui
```

The module must be loaded before the iPod is plugged in (`modules-load.d` loads it at boot). An iPod that is already connected when it loads is switched to the iUI configuration. To keep the module working across kernel updates, install it with DKMS instead: `sudo dkms add ./extras/linux/ipod-iui && sudo dkms install ipod-iui/1.0`. On systems with Secure Boot, the module must be signed. While it is loaded, iPod disks are unavailable; `sudo modprobe -r ipod_iui` and replugging brings them back.

With either the module or the udev rule, `pyusb` is not needed, so `USBHIDTransport(select_configuration=False)` is enough.

#### Linux: USB stops working after unplugging an iPod

On Linux, unplugging an iPod while it is in the iUI configuration can crash the kernel's `apple-mfi-fastcharge` driver (a NULL pointer dereference in `mfi_fc_disconnect`, visible in `journalctl -k`). The crash happens in the USB hub worker, so afterwards new USB devices are no longer detected and shutting down hangs until the machine is forcibly powered off. This is a kernel bug, independent of pyPodControl: `snd-usb-audio`, which binds to the iUI configuration's audio interfaces, overwrites the device data `apple-mfi-fastcharge` relies on. It happens however the configuration is switched, including with the udev rule and the `ipod-iui` module above.

The driver only controls fast charging of iPhones and iPads, so the workaround is to blacklist it and reboot:

```
echo "blacklist apple_mfi_fastcharge" | sudo tee /etc/modprobe.d/no-apple-mfi-fastcharge.conf
```

### Logging

pyPodControl logs through the standard `logging` module, under the `pypodcontrol` logger. Every packet sent to and received from the iPod is logged at DEBUG level to the `pypodcontrol.traffic` logger, with lingo and command names, transaction IDs and decoded ACKs:

```
-> General.RequestLingoProtocolVersion 02
<- General.ReturnLingoProtocolVersion 02 01 03
<- General.ACK (Bad parameter: StartIDPS) 04 38
```

`enable_logging()` prints the library's logs to stderr:

```python
import logging
from pypodcontrol import enable_logging

enable_logging()                             # debug messages and every packet
enable_logging(logging.INFO, traffic=False)  # just what the library is doing
```

With your own logging setup, enable the packet log with `logging.getLogger("pypodcontrol.traffic").setLevel(logging.DEBUG)`. The examples take `-v` for INFO logs and `--debug` for debug logs including every packet.

See the `examples/` directory for complete scripts.

## Development

```sh
pip install -e .[dev]
pytest
```

## Resources

-   [Official iPod Accessory Protocol Specification (archive.org)](https://archive.org/details/ipod-accessory-protocol-interface-specification/)
