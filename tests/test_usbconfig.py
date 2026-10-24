from types import SimpleNamespace

import pytest

from pypodcontrol.errors import TransportError
from pypodcontrol.transport import usbconfig, usbhid
from pypodcontrol.transport.usbconfig import (
    find_iui_configuration,
    select_iui_configuration,
)


class USBError(Exception):
    pass


class NoBackendError(Exception):
    pass


def interface(number, cls):
    return SimpleNamespace(bInterfaceNumber=number, bInterfaceClass=cls)


# Matches an iPod Classic: config 1 mass storage, config 2 audio + HID
MASS_STORAGE = SimpleNamespace(bConfigurationValue=1)
MASS_STORAGE.interfaces = [interface(0, 0x08)]
IUI = SimpleNamespace(bConfigurationValue=2)
IUI.interfaces = [interface(0, 0x01), interface(1, 0x01), interface(1, 0x01), interface(2, 0x03)]


class Config(list):
    def __init__(self, ns):
        super().__init__(ns.interfaces)
        self.bConfigurationValue = ns.bConfigurationValue


class FakeUSBDevice:
    def __init__(self, product_id=0x1261, active=1):
        self.idProduct = product_id
        self.configs = [Config(MASS_STORAGE), Config(IUI)]
        self.active = active
        self.kernel_drivers = {0}
        self.detached = []
        self.disposed = False

    def __iter__(self):
        return iter(self.configs)

    def get_active_configuration(self):
        return next(c for c in self.configs if c.bConfigurationValue == self.active)

    def is_kernel_driver_active(self, number):
        return number in self.kernel_drivers

    def detach_kernel_driver(self, number):
        self.kernel_drivers.discard(number)
        self.detached.append(number)

    def set_configuration(self, value):
        assert not self.kernel_drivers
        self.active = value


@pytest.fixture
def fake_usb(monkeypatch):
    devices = []

    def find(find_all, idVendor, custom_match):
        return [d for d in devices if custom_match(d)]

    def dispose_resources(device):
        device.disposed = True

    core = SimpleNamespace(find=find, USBError=USBError, NoBackendError=NoBackendError)
    util = SimpleNamespace(dispose_resources=dispose_resources)
    monkeypatch.setattr(usbconfig, "_import_pyusb", lambda: (core, util))
    monkeypatch.setattr(usbconfig, "is_mounted", lambda device: False)
    return devices


def test_find_iui_configuration():
    assert find_iui_configuration(FakeUSBDevice()) == 2


def test_switches_from_mass_storage(fake_usb):
    ipod = FakeUSBDevice()
    fake_usb += [FakeUSBDevice(product_id=0x0250), ipod]

    assert select_iui_configuration() == 0x1261
    assert ipod.active == 2
    assert ipod.detached == [0]
    # The opened device handle is released after the switch
    assert ipod.disposed


def test_already_selected(fake_usb):
    ipod = FakeUSBDevice(active=2)
    fake_usb.append(ipod)

    assert select_iui_configuration() == 0x1261
    assert ipod.detached == []


def test_refuses_when_mounted(fake_usb, monkeypatch):
    ipod = FakeUSBDevice()
    fake_usb.append(ipod)
    monkeypatch.setattr(usbconfig, "is_mounted", lambda device: True)

    with pytest.raises(TransportError, match="mounted"):
        select_iui_configuration()
    assert ipod.active == 1

    assert select_iui_configuration(check_mounted=False) == 0x1261
    assert ipod.active == 2


def test_no_ipod(fake_usb):
    with pytest.raises(TransportError):
        select_iui_configuration()


def test_block_devices(tmp_path):
    disk = tmp_path / "8-1:1.0" / "host6" / "block" / "sdb"
    (disk / "sdb2").mkdir(parents=True)
    (disk / "sdb2" / "partition").write_text("2")
    (disk / "queue").mkdir()

    assert usbconfig._block_devices(str(tmp_path)) == {"sdb", "sdb2"}


def test_transport_selects_configuration(monkeypatch):
    from test_usbhid import FakeHID, FakeHIDDevice

    calls = []
    device = FakeHIDDevice([])
    fake_hid = FakeHID(device)
    # HID device appears on the third enumeration
    attempts = [False, False, True]
    enumerate_all = fake_hid.enumerate
    fake_hid.enumerate = lambda vid, pid: enumerate_all(vid, pid) if attempts.pop(0) else []

    monkeypatch.setattr(usbhid, "hid", fake_hid)
    monkeypatch.setattr(usbhid, "sleep", lambda s: None)
    monkeypatch.setattr(
        usbhid,
        "select_iui_configuration",
        lambda vid, pid: calls.append((vid, pid)) or 0x1261,
    )

    transport = usbhid.USBHIDTransport(select_configuration=True)
    transport._open()

    # Configuration selected first, then waited for the HID device to appear
    assert calls == [(0x05AC, None)]
    assert transport.product_id == 0x1261
    assert attempts == []
    assert device.path == b"fake"


def test_transport_wait_times_out(monkeypatch):
    monkeypatch.setattr(usbhid, "hid", object())
    transport = usbhid.USBHIDTransport()
    monkeypatch.setattr(transport, "_find_path", lambda: None)

    with pytest.raises(TransportError, match="iPod USB Interface"):
        transport._wait_for_path(0)
