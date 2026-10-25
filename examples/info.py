import argparse

from common import add_transport_args, make_auth, make_transport
from pypodcontrol import iAPAckError, iAPClient, iAPError
from pypodcontrol.lingo import (
    AccessoryEqualizer,
    AccessoryPower,
    DigitalAudio,
    DisplayRemote,
    ExtendedInterface,
    General,
    Location,
    Microphone,
    RFTuner,
    SimpleRemote,
    Sports,
    Storage,
    USBHostMode,
    iPodOut,
)

LINGOES = [
    General,
    Microphone,
    SimpleRemote,
    DisplayRemote,
    ExtendedInterface,
    AccessoryPower,
    USBHostMode,
    RFTuner,
    AccessoryEqualizer,
    Sports,
    DigitalAudio,
    Storage,
    iPodOut,
    Location,
]
"""Lingoes known to pyPodControl, in lingo ID order"""

BAD_PARAMETER = 0x04
"""ACK status of RequestLingoProtocolVersion for a lingo the iPod doesn't support"""


def info():
    parser = argparse.ArgumentParser(description="Print information about the iPod")
    parser.add_argument(
        "--all-ids",
        action="store_true",
        help="Also query lingo IDs unknown to pyPodControl (0x00-0x3F)",
    )
    add_transport_args(parser)
    args = parser.parse_args()

    with iAPClient(make_transport(args), auth=make_auth(args)) as iap:
        iap.start_identify()

        try:
            print("Name:", iap.general.request_ipod_name())
        except iAPError as e:
            print("Error:", e)

        names = {lingo.LINGO_ID: lingo.__name__ for lingo in LINGOES}
        lingo_ids = range(0x40) if args.all_ids else sorted(names)

        print()
        print("Lingoes:")

        for lingo_id in lingo_ids:
            name = names.get(lingo_id, "(unknown)")

            try:
                major, minor = iap.general.request_lingo_protocol_version(lingo_id)
                status = f"version {major}.{minor:02}"
            except iAPAckError as e:
                if e.status != BAD_PARAMETER:
                    status = f"error: {e}"
                elif lingo_id not in names:
                    continue  # Only list the unknown lingoes the iPod supports
                else:
                    status = "not supported"
            except iAPError as e:
                status = f"error: {e}"

            print(f"  0x{lingo_id:02X} {name:20} {status}")


if __name__ == "__main__":
    info()
