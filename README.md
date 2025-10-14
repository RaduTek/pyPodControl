# pyPodControl

Implementation of Apple iPod Accessory Protocol (iAP) over UART in Python

## How-To

Connect the iPod (or iPhone, or iPad) with a 30 pin docking connector via a breakout cable to a USB->UART adapter, or to a UART port on your SBC (not tested yet).

A 500k resistor on pin 21 may be needed. (In my testing it's been working without one)

**Important**: iPod uses TTL 3.3V serial

## Resources

-   [Official iPod Accessory Protocol Specification (archive.org)](https://archive.org/details/ipod-accessory-protocol-interface-specification/)
