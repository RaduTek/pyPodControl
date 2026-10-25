// SPDX-License-Identifier: GPL-2.0
/*
 * Configure iPods in their iPod USB Interface (iUI) configuration
 *
 * The kernel configures a new USB device while enumerating it, before udev
 * sees it, and picks the iPod's first configuration (mass storage). The iPod
 * reacts by stopping playback and showing its disk mode screen, even when a
 * udev rule switches to the iUI configuration right after.
 *
 * This driver chooses the configuration with a HID interface (iAP over HID,
 * plus USB audio) instead, so the iPod is never put in mass storage mode.
 * It must be loaded before the iPod is plugged in. Its disk is unavailable
 * while this driver is loaded.
 *
 * Needs Linux 6.8 or newer (usb_device_driver.choose_configuration), and
 * conflicts with apple-mfi-fastcharge, which also claims these devices.
 */

#include <linux/module.h>
#include <linux/usb.h>

#define APPLE_VENDOR_ID 0x05ac

static bool ipod_iui_match(struct usb_device *udev)
{
	u16 vendor = le16_to_cpu(udev->descriptor.idVendor);
	u16 product = le16_to_cpu(udev->descriptor.idProduct);

	/* iPods, iPhones and iPads with more than one configuration */
	return vendor == APPLE_VENDOR_ID && (product & 0xff00) == 0x1200 &&
	       udev->descriptor.bNumConfigurations > 1;
}

static int ipod_iui_choose_configuration(struct usb_device *udev)
{
	int i, j;

	for (i = 0; i < udev->descriptor.bNumConfigurations; i++) {
		struct usb_host_config *config = &udev->config[i];

		for (j = 0; j < config->desc.bNumInterfaces; j++) {
			struct usb_interface_cache *intfc = config->intf_cache[j];

			if (intfc && intfc->num_altsetting &&
			    intfc->altsetting[0].desc.bInterfaceClass == USB_CLASS_HID)
				return config->desc.bConfigurationValue;
		}
	}

	/* No iUI configuration, let the kernel choose as usual */
	return -ENODEV;
}

static struct usb_device_driver ipod_iui_driver = {
	.name = "ipod-iui",
	.match = ipod_iui_match,
	.choose_configuration = ipod_iui_choose_configuration,
	.generic_subclass = 1,
	.supports_autosuspend = 1,
};

static int __init ipod_iui_init(void)
{
	return usb_register_device_driver(&ipod_iui_driver, THIS_MODULE);
}

static void __exit ipod_iui_exit(void)
{
	usb_deregister_device_driver(&ipod_iui_driver);
}

module_init(ipod_iui_init);
module_exit(ipod_iui_exit);

MODULE_DESCRIPTION("Configure iPods in their iPod USB Interface configuration");
MODULE_LICENSE("GPL");
