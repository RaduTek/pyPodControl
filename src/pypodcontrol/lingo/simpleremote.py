from pypodcontrol.iapbase import iAPBase
from . import Lingo


class SimpleRemote(Lingo):
    """
    ### SimpleRemote Lingo (0x02)

    Implements basic remote control of iPod (button presses)
    """

    # Available buttons, sorted in order of the bitmask
    buttons = [
        "play_pause",
        "volume_up",
        "volume_down",
        "next_track",
        "previous_track",
        "next_album",
        "previous_album",
        "stop",
        "play",
        "pause",
        "mute",
        "next_chapter",
        "previous_chapter",
        "shuffle",
        "repeat",
        "power_on",
        "power_off",
        "backlight",
        "fast_forward",
        "rewind",
        "menu",
        "select",
        "up",
        "down",
        "backlight_off",
    ]

    current_buttons = set()

    def __init__(self, iap: iAPBase) -> None:
        """Create a new instance of SimpleRemote"""

        # 0x02 is the Lingo ID for SimpleRemote
        super().__init__(iap, 0x02)

    @staticmethod
    def get_button_mask(button: str) -> int:
        """Returns the matching bit mask for the button"""

        index = SimpleRemote.buttons.index(button)

        return 1 << index

    @staticmethod
    def encode_mask(mask: int) -> bytes:
        """Encode the button mask in the shortest byte string"""
        if mask == 0:
            return b"\x00"

        length = (mask.bit_length() + 7) // 8
        return mask.to_bytes(length, "little")

    def update_buttons(self) -> None:
        mask = 0

        for button in self.current_buttons:
            mask |= SimpleRemote.get_button_mask(button)

        self.send_command(0x00, SimpleRemote.encode_mask(mask))

    def get_button_state(self, button: str) -> bool:
        """Check if a button is pressed"""

        return button in self.current_buttons

    def hold_button(self, button: str) -> None:
        """Hold a button"""

        if self.get_button_state(button):
            return

        self.current_buttons.add(button)
        self.update_buttons()

    def release_button(self, button: str) -> None:
        """Release a button"""

        if not self.get_button_state(button):
            return

        self.current_buttons.remove(button)
        self.update_buttons()

    def press_button(self, button: str) -> None:
        """Press a button"""

        self.hold_button(button)
        self.release_button(button)
