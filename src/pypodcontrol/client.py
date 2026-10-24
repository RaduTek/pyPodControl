import logging
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, TypeVar

from serial import Serial

from .auth import AuthenticationProvider
from .errors import iAPAckError, iAPError, iAPTimeoutError
from .lingo import General, Lingo
from .packet import Packet
from .transport import Transport, UARTTransport

logger = logging.getLogger(__name__)

L = TypeVar("L", bound=Lingo)


@dataclass(eq=False)
class _Pending:
    """A request waiting for its response"""

    lingo: Lingo
    command_id: int
    response_ids: frozenset[int]
    transaction_id: int | None
    deadline: float
    future: Future = field(default_factory=Future)


class iAPClient:
    """
    ### iAPClient

    Glues together a Transport and the registered Lingos

    Encodes outgoing commands, decodes incoming packets and routes them either
    to the request waiting for them, or to the lingo they belong to.
    """

    transport: Transport
    """Transport link to the iPod"""

    timeout: float
    """Default response timeout, in seconds"""

    def __init__(
        self,
        transport: Transport | str | Serial,
        *,
        auth: AuthenticationProvider | None = None,
        use_idps: bool = False,
        timeout: float = 2.0,
    ) -> None:
        """
        Create a new iAPClient

        - transport: Transport to use, or a serial port name / Serial instance for UART
        - auth: Authentication provider, required for IDPS
        - use_idps: Identify using IDPS (with transaction IDs) instead of the legacy process
        - timeout: Default response timeout, in seconds
        """

        if use_idps and auth is None:
            raise ValueError("IDPS requires an AuthenticationProvider")

        if not isinstance(transport, Transport):
            transport = UARTTransport(transport)

        self.transport = transport
        self.timeout = timeout

        self._auth = auth
        self._use_idps = use_idps

        self._lingos: dict[int, Lingo] = {}
        self._pending: list[_Pending] = []
        self._lock = threading.Lock()

        self._transaction_id = 0
        self._transaction_ids_enabled = False

        self._general = self.register(General())

    @property
    def auth(self) -> AuthenticationProvider | None:
        """Authentication provider"""

        return self._auth

    @property
    def use_idps(self) -> bool:
        """Whether the accessory identifies using IDPS"""

        return self._use_idps

    @property
    def general(self) -> General:
        """General lingo, always registered"""

        return self._general

    @property
    def lingos(self) -> Mapping[int, Lingo]:
        """Registered lingos, by lingo ID"""

        return MappingProxyType(self._lingos)

    @property
    def transaction_ids_enabled(self) -> bool:
        """
        Whether transaction IDs are included in packets

        Enabled on open when using IDPS, and managed by the protocol afterwards
        """

        return self._transaction_ids_enabled

    @transaction_ids_enabled.setter
    def transaction_ids_enabled(self, enabled: bool) -> None:
        self._transaction_ids_enabled = enabled

    @property
    def is_open(self) -> bool:
        """Whether the transport is open"""

        return self.transport.is_open

    def register(self, lingo: L | type[L]) -> L:
        """
        Register a lingo with this client and return it

        Accepts a lingo instance or a Lingo subclass (which gets instantiated)
        """

        if isinstance(lingo, type):
            lingo = lingo()

        if not isinstance(lingo, Lingo):
            raise TypeError("lingo must be a Lingo instance or subclass")

        existing = self._lingos.get(lingo.LINGO_ID)
        if existing is lingo:
            return lingo
        if existing is not None:
            raise iAPError(
                f"Lingo 0x{lingo.LINGO_ID:02X} is already registered as {type(existing).__name__}"
            )

        lingo._bind(self)
        self._lingos[lingo.LINGO_ID] = lingo

        return lingo

    def unregister(self, lingo: Lingo | type[Lingo] | int) -> None:
        """Unregister a lingo"""

        lingo_id = lingo if isinstance(lingo, int) else lingo.LINGO_ID

        if lingo_id == General.LINGO_ID:
            raise ValueError("The General lingo cannot be unregistered")

        instance = self._lingos.pop(lingo_id, None)
        if instance is not None:
            instance._unbind()

    def get(self, lingo: type[L] | int) -> L | None:
        """Get a registered lingo by class or lingo ID"""

        lingo_id = lingo if isinstance(lingo, int) else lingo.LINGO_ID
        return self._lingos.get(lingo_id)  # type: ignore[return-value]

    def __contains__(self, lingo: Lingo | type[Lingo] | int) -> bool:
        lingo_id = lingo if isinstance(lingo, int) else lingo.LINGO_ID
        return lingo_id in self._lingos

    def open(self) -> None:
        """Open the transport and start receiving packets"""

        if self.is_open:
            return

        self._transaction_id = 0
        self._transaction_ids_enabled = self._use_idps

        self.transport.set_receiver(self._on_payload)
        self.transport.open()
        self.transport.wake()

    def close(self) -> None:
        """Close the transport, failing any pending requests"""

        self.transport.close()
        self.transport.set_receiver(None)

        with self._lock:
            pending, self._pending = self._pending, []

        for p in pending:
            p.future.set_exception(iAPError("Client closed"))

    def __enter__(self) -> "iAPClient":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _next_transaction_id(self) -> int:
        with self._lock:
            transaction_id = self._transaction_id
            self._transaction_id = (self._transaction_id + 1) & 0xFFFF
            return transaction_id

    def _build_packet(
        self, lingo: Lingo, command_id: int, data: bytes, transaction_id: bool | None
    ) -> Packet:
        if transaction_id is None:
            transaction_id = self._transaction_ids_enabled

        return Packet(
            lingo.LINGO_ID,
            command_id,
            data,
            self._next_transaction_id() if transaction_id else None,
        )

    def _send(self, lingo: Lingo, packet: Packet) -> None:
        logger.debug(
            "-> %s.%s %s",
            type(lingo).__name__,
            lingo.command_name(packet.command_id),
            packet.data.hex(" "),
        )
        self.transport.send(packet.to_payload(lingo.EXTENDED_COMMAND_IDS))

    def send_packet(
        self,
        lingo: Lingo,
        command_id: int,
        data: bytes = b"",
        *,
        transaction_id: bool | None = None,
    ) -> Packet:
        """
        Send a command without waiting for a response, returns the sent packet

        - transaction_id: Override whether a transaction ID is included
        """

        packet = self._build_packet(lingo, command_id, data, transaction_id)
        self._send(lingo, packet)
        return packet

    def request(
        self,
        lingo: Lingo,
        command_id: int,
        data: bytes = b"",
        response_ids: frozenset[int] = frozenset(),
        timeout: float | None = None,
    ) -> Packet:
        """
        Send a command and block until its response arrives

        - response_ids: Command IDs of the expected response, empty to wait for an ACK
        - timeout: Timeout in seconds, None for the default timeout

        Returns the response packet (or the ACK packet)
        """

        if timeout is None:
            timeout = self.timeout

        packet = self._build_packet(lingo, command_id, data, None)
        pending = _Pending(
            lingo,
            command_id,
            response_ids,
            packet.transaction_id,
            time.monotonic() + timeout,
        )

        # Register before sending, the response may arrive before send returns
        with self._lock:
            self._pending.append(pending)

        try:
            self._send(lingo, packet)
            return self._wait(pending)
        finally:
            with self._lock:
                if pending in self._pending:
                    self._pending.remove(pending)

    def _wait(self, pending: _Pending) -> Packet:
        while True:
            remaining = pending.deadline - time.monotonic()

            try:
                return pending.future.result(timeout=max(remaining, 0))
            except FutureTimeoutError:
                # Deadline may have been extended by a command pending ACK
                if pending.deadline > time.monotonic():
                    continue

                raise iAPTimeoutError(
                    f"No response to {type(pending.lingo).__name__}."
                    f"{pending.lingo.command_name(pending.command_id)} in time"
                ) from None

    def _decode(self, payload: bytes) -> tuple[Lingo | None, Packet]:
        lingo = self._lingos.get(payload[0]) if payload else None
        extended = lingo.EXTENDED_COMMAND_IDS if lingo is not None else False

        has_transaction_id = self._transaction_ids_enabled

        if has_transaction_id and payload[0] == General.LINGO_ID and len(payload) >= 2:
            command_id = payload[1]

            # RequestIdentify, and ACKs from iPods without transaction ID
            # support, never carry a transaction ID
            if command_id == General.COMMANDS["RequestIdentify"] or (
                command_id == General.COMMANDS["ACK"] and len(payload) in (4, 8)
            ):
                has_transaction_id = False
                self._transaction_ids_enabled = False
                logger.info("Transaction IDs disabled by iPod")

        return lingo, Packet.from_payload(payload, extended, has_transaction_id)

    def _on_payload(self, payload: bytes) -> None:
        """Handle a payload received by the transport (reader thread)"""

        try:
            lingo, packet = self._decode(payload)
        except ValueError:
            logger.warning("Dropping malformed packet %s", payload.hex(" "))
            return

        if lingo is None:
            logger.debug(
                "<- unregistered lingo 0x%02X command 0x%02X %s",
                packet.lingo_id,
                packet.command_id,
                packet.data.hex(" "),
            )
            return

        logger.debug(
            "<- %s.%s %s",
            type(lingo).__name__,
            lingo.command_name(packet.command_id),
            packet.data.hex(" "),
        )

        if self._resolve_pending(lingo, packet):
            return

        lingo.handle_packet(packet)

    def _resolve_pending(self, lingo: Lingo, packet: Packet) -> bool:
        """Complete the request this packet responds to, returns whether one matched"""

        ack = lingo.parse_ack(packet)

        with self._lock:
            for pending in self._pending:
                if pending.lingo is not lingo or pending.future.done():
                    continue

                if (
                    pending.transaction_id is not None
                    and packet.transaction_id is not None
                    and pending.transaction_id != packet.transaction_id
                ):
                    continue

                if packet.command_id in pending.response_ids:
                    pending.future.set_result(packet)
                    return True

                if ack is None or ack[1] != pending.command_id:
                    continue

                status = ack[0]

                if status == lingo.ACK_PENDING:
                    # Command pending ACKs end with the maximum wait in ms
                    if len(packet.data) >= 6:
                        wait = int.from_bytes(packet.data[-4:], "big") / 1000.0
                        pending.deadline = max(
                            pending.deadline, time.monotonic() + wait
                        )
                    return True

                if status != lingo.ACK_SUCCESS:
                    pending.future.set_exception(
                        iAPAckError(
                            status,
                            f"{type(lingo).__name__}.{lingo.command_name(pending.command_id)}",
                        )
                    )
                    return True

                # Success ACK completes requests that expect no other response
                if not pending.response_ids:
                    pending.future.set_result(packet)
                return True

        return False
