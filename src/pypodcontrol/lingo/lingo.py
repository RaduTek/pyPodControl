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

    def close(self) -> None:
        """
        Notify the iPod of the lingo's departure and release per-connection state

        Called by iAPClient.close() for every registered lingo, and by
        unregister() before the lingo is unbound, while the transport is still
        open, so an override may send a parting command to the iPod (e.g. leave
        a mode it entered). It is best-effort: the iPod may have already
        disconnected (sends then raise TransportError at once), and listeners
        may still be running, so keep it quick and thread-safe. The default
        does nothing.
        """

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
        *,
        transaction_id: bool | int | None = None,
    ) -> Packet:
        """
        Send a command and wait for the iPod's response

        - command: Command name or ID
        - data: Command parameters
        - response: Expected response command(s), or None to wait for an ACK
        - timeout: Timeout in seconds, None for the client's default
        - transaction_id: Override whether a transaction ID is included
          (True/False), or an explicit ID to send

        Raises iAPAckError if the iPod responds with an error ACK, and
        iAPTimeoutError if no response is received in time.
        """

        return self.iap.request(
            self,
            self.command_id(command),
            data,
            self._response_ids(response),
            timeout,
            transaction_id=transaction_id,
        )

    def request_multiple(
        self,
        command: str | int,
        data: bytes = b"",
        response: str | int | Iterable[str | int] | None = None,
        done: Callable[[list[Packet]], bool] | None = None,
        timeout: float | None = None,
        idle_timeout: float = 0.3,
    ) -> list[Packet]:
        """
        Send a command and gather the response packets it produces

        - command: Command name or ID
        - data: Command parameters
        - response: Expected response command(s)
        - done: Called after each packet with all packets so far, returns
          whether all have been received; None to end on the iPod's ACK or
          when no packet arrives for idle_timeout seconds
        - timeout: Timeout for the first packet, None for the client's default
        - idle_timeout: Maximum gap between packets, in seconds

        Raises iAPAckError if the iPod responds with an error ACK, and
        iAPTimeoutError if no response is received in time.
        """

        return self.iap.request_multiple(
            self,
            self.command_id(command),
            data,
            self._response_ids(response),
            done,
            timeout,
            idle_timeout,
        )

    def _response_ids(
        self, response: str | int | Iterable[str | int] | None
    ) -> frozenset[int]:
        if response is None:
            return frozenset()
        if isinstance(response, (str, int)):
            return frozenset([self.command_id(response)])
        return frozenset(self.command_id(r) for r in response)

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
        """
        Call listener whenever the iPod sends the given command unsolicited

        Listeners run on the client's event thread (see iAPClient.dispatch()),
        so they may block and send requests to the iPod.
        """

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
        commands sent by the iPod, call super() for the commands the override
        doesn't handle, or notify_listeners() for the ones it does.
        """

        if not self.notify_listeners(packet):
            logger.debug(
                "%s: unhandled %s", type(self).__name__, self.command_name(packet.command_id)
            )

    def notify_listeners(self, packet: Packet) -> bool:
        """
        Call the listeners of the packet's command on the client's event
        thread, returns whether it has any
        """

        listeners = list(self._listeners.get(packet.command_id, []))

        def run() -> None:
            for listener in listeners:
                try:
                    listener(packet)
                except Exception:
                    logger.exception(
                        "%s: listener for %s failed",
                        type(self).__name__,
                        self.command_name(packet.command_id),
                    )

        if listeners:
            self.iap.dispatch(run)

        return bool(listeners)
