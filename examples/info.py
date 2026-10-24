import argparse

from common import add_transport_args, make_auth, make_transport
from pypodcontrol import iAPClient, iAPError
from pypodcontrol.lingo import General, SimpleRemote


def info():
    parser = argparse.ArgumentParser(description="Print information about the iPod")
    add_transport_args(parser)
    args = parser.parse_args()

    with iAPClient(make_transport(args), auth=make_auth(args)) as iap:
        iap.register(SimpleRemote)
        iap.start_identify()

        try:
            print("Name:", iap.general.request_ipod_name())

            for lingo in (General, SimpleRemote):
                major, minor = iap.general.request_lingo_protocol_version(lingo)
                print(f"{lingo.__name__} lingo version: {major}.{minor:02}")
        except iAPError as e:
            print("Error:", e)


if __name__ == "__main__":
    info()
