import logging
from typing import TYPE_CHECKING, Callable, ClassVar, Iterable

from ..errors import iAPError
from ..packet import Packet

if TYPE_CHECKING:
    from ..client import iAPClient

logger = logging.getLogger(__name__)

Listener = Callable[[Packet], None]
"""Callback invoked with an unsolicited packet received from the iPod"""


class Lingo:
    """
    ### Lingo

    Base class for an iAP Lingo

    Extend this class to implement different iAP Lingos, then register an
    instance with `iAPClient.register()`
    """

    LINGO_ID: ClassVar[int]
    """Lingo ID"""

    COMMANDS: ClassVar[dict[str, int]] = {}
    """Known commands, mapping command names to IDs"""

    COMMAND_NAMES: ClassVar[dict[int, str]] = {}
    """Known commands, mapping command IDs to names (built from COMMANDS)"""

    EXTENDED_COMMAND_IDS: ClassVar[bool] = False
    """Whether this lingo uses 2 byte command IDs"""

    ACK_COMMAND: ClassVar[str | None] = None
    """Name of the command the iPod uses to acknowledge commands of this lingo"""

    ACK_SUCCESS: ClassVar[int] = 0x00
    """ACK status: success"""

    ACK_PENDING: ClassVar[int] = 0x06
    """ACK status: command pending"""

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        names: dict[int, str] = {}
        for name, command_id in cls.COMMANDS.items():
            if command_id in names:
                raise ValueError(
                    f"{cls.__name__}: {name} and {names[command_id]} share command ID 0x{command_id:02X}"
                )
            names[command_id] = name

        cls.COMMAND_NAMES = names

    def __init__(self) -> None:
        """Create a new instance of the lingo, to be registered with an iAPClient"""

        self._client: "iAPClient | None" = None
        self._listeners: dict[int, list[Listener]] = {}

    @property
    def iap(self) -> "iAPClient":
        """The iAPClient this lingo is registered with"""

        if self._client is None:
            raise iAPError(f"{type(self).__name__} is not registered with an iAPClient")

        return self._client

    @property
    def is_registered(self) -> bool:
        """Whether this lingo is registered with an iAPClient"""

        return self._client is not None

    def _bind(self, client: "iAPClient") -> None:
        """Bind to a client, called by iAPClient.register()"""

        if self._client is not None and self._client is not client:
            raise iAPError(f"{type(self).__name__} is registered with another iAPClient")

        self._client = client

    def _unbind(self) -> None:
        """Unbind from the client, called by iAPClient.unregister()"""

        self._client = None

    @classmethod
    def command_id(cls, command: str | int) -> int:
        """Get the ID of given command"""

        if isinstance(command, int):
            return command

        try:
            return cls.COMMANDS[command]
        except KeyError:
            raise KeyError(f"{cls.__name__} has no command {command!r}") from None

    @classmethod
    def command_name(cls, command_id: int) -> str:
        """Get the name of given command ID"""

        width = 4 if cls.EXTENDED_COMMAND_IDS else 2
        return cls.COMMAND_NAMES.get(command_id, f"Unknown(0x{command_id:0{width}X})")

    def send(
        self,
        command: str | int,
        data: bytes = b"",
        *,
        transaction_id: bool | int | None = None,
    ) -> Packet:
        """
        Send a command without waiting for a response

        - command: Command name or ID
        - data: Command parameters
        - transaction_id: Override whether a transaction ID is included
          (True/False), or an explicit ID to send
        """

        return self.iap.send_packet(
            self, self.command_id(command), data, transaction_id=transaction_id
        )

    def request(
        self,
        command: str | int,
        data: bytes = b"",
        response: str | int | Iterable[str | int] | None = None,
        timeout: float | None = None,
    ) -> Packet:
        """
        Send a command and wait for the iPod's response

        - command: Command name or ID
        - data: Command parameters
        - response: Expected response command(s), or None to wait for an ACK
        - timeout: Timeout in seconds, None for the client's default

        Raises iAPAckError if the iPod responds with an error ACK, and
        iAPTimeoutError if no response is received in time.
        """

        if response is None:
            response_ids = frozenset()
        elif isinstance(response, (str, int)):
            response_ids = frozenset([self.command_id(response)])
        else:
            response_ids = frozenset(self.command_id(r) for r in response)

        return self.iap.request(
            self, self.command_id(command), data, response_ids, timeout
        )

    def parse_ack(self, packet: Packet) -> tuple[int, int] | None:
        """
        Parse an ACK packet of this lingo

        Returns (status, acknowledged command ID), or None if the packet is not an ACK
        """

        if self.ACK_COMMAND is None or packet.command_id != self.command_id(
            self.ACK_COMMAND
        ):
            return None

        width = 2 if self.EXTENDED_COMMAND_IDS else 1
        if len(packet.data) < 1 + width:
            return None

        return packet.data[0], int.from_bytes(packet.data[1 : 1 + width], "big")

    def add_listener(self, command: str | int, listener: Listener) -> None:
        """Call listener whenever the iPod sends the given command unsolicited"""

        self._listeners.setdefault(self.command_id(command), []).append(listener)

    def remove_listener(self, command: str | int, listener: Listener) -> None:
        """Remove a listener added with add_listener()"""

        listeners = self._listeners.get(self.command_id(command), [])
        if listener in listeners:
            listeners.remove(listener)

    def handle_packet(self, packet: Packet) -> None:
        """
        Handle an unsolicited packet from the iPod

        Called on the transport's reader thread. Override to react to
        commands sent by the iPod, call super() to keep notifying listeners.
        """

        listeners = self._listeners.get(packet.command_id, [])

        if not listeners:
            logger.debug(
                "%s: unhandled %s %s",
                type(self).__name__,
                self.command_name(packet.command_id),
                packet.data.hex(" "),
            )

        for listener in list(listeners):
            try:
                listener(packet)
            except Exception:
                logger.exception(
                    "%s: listener for %s failed",
                    type(self).__name__,
                    self.command_name(packet.command_id),
                )
