import argparse

from common import add_transport_args, make_auth, make_transport
from pypodcontrol import iAPClient
from pypodcontrol.lingo import AccessoryEqualizer
from pypodcontrol.packet import Packet, encode_byte, encode_int


def accessory_equalizer():
    parser = argparse.ArgumentParser(
        description="Print the iPod's track changes, play state and volume as they happen"
    )
    parser.add_argument(
        "--position", action="store_true", help="Also print the track position every second"
    )
    add_transport_args(parser)
    args = parser.parse_args()

    with iAPClient(make_transport(args), auth=make_auth(args)) as iap:
        eq = iap.register(AccessoryEqualizer)
        iap.start_identify()

        eq_settings = ["Bass Boost", "Treble Boost", "Vocal Boost", "Flat", "Rock", "Pop", "Jazz", "Classical"]
        eq_index = 3

        def ret_eq_setting_count(packet: Packet) -> None:
            eq.send("RetEQSettingCount", encode_byte(len(eq_settings)))

        eq.add_listener("GetEQSettingCount", ret_eq_setting_count)

        def ret_eq_index_name(packet: Packet) -> None:
            index = packet.data[0]
            if index < len(eq_settings):
                eq.send("RetEQIndexName", encode_byte(index) + eq_settings[index].encode("utf-8"))
            else:
                eq.send("RetEQIndexName", encode_byte(index) + b"")

        eq.add_listener("GetEQIndexName", ret_eq_index_name)

        def ret_current_eq_index(packet: Packet) -> None:
            eq.send("RetCurrentEQIndex", encode_byte(eq_index))

        eq.add_listener("GetCurrentEQIndex", ret_current_eq_index)

        def set_current_eq_index(packet: Packet) -> None:
            nonlocal eq_index
            index = packet.data[0]
            if index < len(eq_settings):
                eq_index = index
                print(f"EQ index set to {eq_index} ({eq_settings[eq_index]})")
                eq.send("AccessoryAck", encode_byte(0x00) + encode_byte(packet.command_id))
            else:
                print(f"Invalid EQ index {index}")

        eq.add_listener("SetCurrentEQIndex", set_current_eq_index)

        print("Waiting for events, press Ctrl+C to quit")

        try:
            iap.wait_until_closed()
            print("iPod disconnected")
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    accessory_equalizer()
