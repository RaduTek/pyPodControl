import logging
import queue
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Mapping, TypeVar

from serial import Serial

from .auth import AuthenticationProvider
from .debug import ack_status_name, log_packet
from .errors import (
    iAPAckError,
    iAPError,
    iAPIdentificationError,
    iAPTimeoutError,
)
from .lingo import General, Lingo
from .lingo.general import AccessoryInfo, PowerOption
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


@dataclass(eq=False)
class _Collector:
    """A request gathering several response packets"""

    lingo: Lingo
    command_id: int
    response_ids: frozenset[int]
    transaction_id: int | None
    packets: queue.SimpleQueue = field(default_factory=queue.SimpleQueue)
    """Received packets, or the exception to raise in the waiting thread"""


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
        accessory_info: AccessoryInfo | None = None,
        timeout: float = 2.0,
    ) -> None:
        """
        Create a new iAPClient

        - transport: Transport to use, or a serial port name / Serial instance for UART
        - auth: Authentication provider, required for IDPS
        - use_idps: Identify using IDPS (with transaction IDs) instead of the legacy process
        - accessory_info: Accessory information sent during IDPS
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
        self.accessory_info = accessory_info or AccessoryInfo()

        self._identify_args: tuple[bool, PowerOption] | None = None

        self._lingos: dict[int, Lingo] = {}
        self._pending: list[_Pending] = []
        self._collectors: list[_Collector] = []
        self._lock = threading.Lock()

        self._transaction_id = 0
        self._transaction_ids_enabled = False

        self._events: queue.SimpleQueue[Callable[[], None] | None] = queue.SimpleQueue()
        self._event_thread: threading.Thread | None = None

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
    def is_identified(self) -> bool:
        """Whether start_identify() completed since the client was opened"""

        return self._identify_args is not None

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
            instance.close()
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
        self._identify_args = None

        logger.info("Opening %s", type(self.transport).__name__)

        self._event_thread = threading.Thread(
            target=self._run_events, name="iAP-events", daemon=True
        )
        self._event_thread.start()

        self.transport.set_receiver(self._on_payload)
        self.transport.open()
        self.transport.wake()

    def close(self) -> None:
        """Close the transport, failing any pending requests"""

        self.transport.close()
        self.transport.set_receiver(None)

        # Let the listeners finish the events already received
        if self._event_thread is not None:
            self._events.put(None)
            if self._event_thread is not threading.current_thread():
                self._event_thread.join()
            self._event_thread = None

        with self._lock:
            pending, self._pending = self._pending, []
            collectors, self._collectors = self._collectors, []

        logger.info("Closed %s", type(self.transport).__name__)
        if pending:
            logger.debug("Failing %d pending request(s)", len(pending))

        for p in pending:
            p.future.set_exception(iAPError("Client closed"))

        for c in collectors:
            c.packets.put(iAPError("Client closed"))

        # Let each lingo release per-connection state (after the event thread
        # has stopped, so no listener runs concurrently)
        for lingo in self._lingos.values():
            try:
                lingo.close()
            except Exception:
                logger.exception("%s: close() failed", type(lingo).__name__)

    def wait_until_closed(self, timeout: float | None = None) -> bool:
        """
        Block until the client is closed or the iPod disconnects, returns
        whether it closed (False on timeout)

        Use this in event driven scripts to keep the main thread alive while
        listeners handle the iPod's notifications. Ctrl+C interrupts the wait
        with KeyboardInterrupt.

        - timeout: How long to wait, in seconds, None to wait indefinitely
        """

        deadline = None if timeout is None else time.monotonic() + timeout

        # Wait in short steps, so KeyboardInterrupt is delivered promptly
        while True:
            step = 0.5 if deadline is None else min(0.5, deadline - time.monotonic())
            if step <= 0:
                return False
            if self.transport.wait_closed(step):
                return True

    def dispatch(self, callback: Callable[[], None]) -> None:
        """
        Run a callback on the client's event thread

        Listeners run on this thread, in the order the iPod's packets were
        received. Unlike the transport's reader thread, it may block and send
        requests to the iPod.
        """

        if self._event_thread is None:
            raise iAPError("Client is not open")

        self._events.put(callback)

    def _run_events(self) -> None:
        """Event thread, runs dispatched callbacks until close()"""

        while True:
            callback = self._events.get()
            if callback is None:
                return

            try:
                callback()
            except Exception:
                logger.exception("Event callback failed")

    def __enter__(self) -> "iAPClient":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def start_identify(
        self,
        authenticate: bool | None = None,
        power_options: PowerOption = PowerOption.LOW_POWER,
        auth_timeout: float = 10.0,
    ) -> None:
        """
        Identify the accessory and all registered lingoes to the iPod

        Uses IDPS when the client was created with use_idps=True (falling back
        to IdentifyDeviceLingoes if the iPod doesn't support IDPS), otherwise
        IdentifyDeviceLingoes. When authentication is requested, this returns
        once the iPod reports the authentication result.

        - authenticate: Request immediate authentication (Authentication 2.0),
          None to authenticate when an AuthenticationProvider is set. Required by IDPS.
        - power_options: Power the accessory draws from the iPod
        - auth_timeout: How long to wait for authentication to finish, in seconds

        Raises iAPAckError or iAPIdentificationError if the iPod rejects the
        identification or authentication.
        """

        if authenticate is None:
            authenticate = self._auth is not None

        if authenticate and self._auth is None:
            raise ValueError("Authentication requires an AuthenticationProvider")

        if self._use_idps and not authenticate:
            raise ValueError("IDPS requires authentication")

        options = General.identify_options(authenticate, power_options)
        device_id = self._auth.device_id if authenticate and self._auth else 0
        lingo_ids = sorted(self._lingos)

        self._identify_args = None

        logger.info(
            "Identifying lingoes %s using %s, %s",
            ", ".join(type(lingo).__name__ for _, lingo in sorted(self._lingos.items())),
            "IDPS" if self._use_idps else "IdentifyDeviceLingoes",
            "with authentication" if authenticate else "without authentication",
        )

        if authenticate:
            # The iPod drives authentication right after identification; the
            # General lingo answers its requests on the reader thread
            self.general.reset_authentication()

        if self._use_idps:
            try:
                self.general.run_idps(lingo_ids, options, device_id, self.accessory_info)
            except iAPAckError as e:
                # Bad parameter: the iPod doesn't support IDPS
                if e.status != 0x04 or e.command != "General.StartIDPS":
                    raise

                logger.info("iPod doesn't support IDPS, using IdentifyDeviceLingoes")
                self.general.identify_device_lingoes(lingo_ids, options, device_id)
        else:
            self.general.identify_device_lingoes(lingo_ids, options, device_id)

        if authenticate and not self.general.wait_for_authentication(auth_timeout):
            status = self.general.authentication_status
            raise iAPIdentificationError(
                "Authentication timed out"
                if status is None
                else f"Authentication failed with status 0x{status:02X}"
            )

        self._identify_args = (authenticate, power_options)
        logger.info("Identified")

    def wait_for_authentication(self, timeout: float | None = None) -> bool:
        """
        Wait for device authentication to finish, returns whether it passed

        `start_identify()` already waits when authentication is requested; use
        this to wait again, for example after the iPod re-requests identification.

        - timeout: How long to wait, in seconds, None to wait indefinitely
        """

        return self.general.wait_for_authentication(timeout)

    @property
    def is_authenticated(self) -> bool:
        """Whether device authentication has passed"""

        return self.general.authentication_status == General.AUTH_SUCCESS

    def reidentify(self) -> None:
        """Repeat the last start_identify(), e.g. when the iPod sends RequestIdentify"""

        if self._identify_args is None:
            raise iAPError("start_identify() was not called")

        try:
            self.start_identify(*self._identify_args)
        except iAPError:
            logger.exception("Identifying again failed")

    def next_transaction_id(self) -> int:
        """Allocate the next transaction ID, e.g. to share one across the sections of a command"""

        with self._lock:
            transaction_id = self._transaction_id
            self._transaction_id = (self._transaction_id + 1) & 0xFFFF
            return transaction_id

    def _build_packet(
        self,
        lingo: Lingo,
        command_id: int,
        data: bytes,
        transaction_id: bool | int | None,
    ) -> Packet:
        if transaction_id is None:
            transaction_id = self._transaction_ids_enabled

        if transaction_id is True:
            tid: int | None = self.next_transaction_id()
        elif transaction_id is False:
            tid = None
        else:
            # An explicit transaction ID, e.g. echoed back on an auth response
            tid = transaction_id

        return Packet(lingo.LINGO_ID, command_id, data, tid)

    def _send(self, lingo: Lingo, packet: Packet) -> None:
        log_packet("->", lingo, packet)
        self.transport.send(packet.to_payload(lingo.EXTENDED_COMMAND_IDS))

    def send_packet(
        self,
        lingo: Lingo,
        command_id: int,
        data: bytes = b"",
        *,
        transaction_id: bool | int | None = None,
    ) -> Packet:
        """
        Send a command without waiting for a response, returns the sent packet

        - transaction_id: Override whether a transaction ID is included
          (True/False), or an explicit ID to send
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
        *,
        transaction_id: bool | int | None = None,
    ) -> Packet:
        """
        Send a command and block until its response arrives

        - response_ids: Command IDs of the expected response, empty to wait for an ACK
        - timeout: Timeout in seconds, None for the default timeout
        - transaction_id: Override whether a transaction ID is included
          (True/False), or an explicit ID to send

        Returns the response packet (or the ACK packet)
        """

        if timeout is None:
            timeout = self.timeout

        packet = self._build_packet(lingo, command_id, data, transaction_id)
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

    def request_multiple(
        self,
        lingo: Lingo,
        command_id: int,
        data: bytes = b"",
        response_ids: frozenset[int] = frozenset(),
        done: Callable[[list[Packet]], bool] | None = None,
        timeout: float | None = None,
        idle_timeout: float = 0.3,
    ) -> list[Packet]:
        """
        Send a command and gather the response packets it produces

        For commands the iPod answers with several packets (one per record,
        or the sections of a large transfer). Gathering ends when done(packets)
        returns True, the iPod sends a success ACK, or no packet arrives for
        idle_timeout seconds after the first one.

        - response_ids: Command IDs of the expected responses
        - done: Called after each packet with all packets so far, None to
          end on the ACK or the idle timeout only
        - timeout: Timeout for the first packet, None for the default timeout
        - idle_timeout: Maximum gap between packets, in seconds

        Raises iAPAckError if the iPod responds with an error ACK, and
        iAPTimeoutError if no packet is received in time.
        """

        if timeout is None:
            timeout = self.timeout

        packet = self._build_packet(lingo, command_id, data, None)
        collector = _Collector(lingo, command_id, response_ids, packet.transaction_id)
        name = f"{type(lingo).__name__}.{lingo.command_name(command_id)}"

        # Register before sending, the responses may arrive before send returns
        with self._lock:
            self._collectors.append(collector)

        try:
            self._send(lingo, packet)

            packets: list[Packet] = []
            deadline = time.monotonic() + timeout

            while True:
                wait = idle_timeout if packets else deadline - time.monotonic()

                try:
                    item = collector.packets.get(timeout=max(wait, 0))
                except queue.Empty:
                    if packets:
                        return packets
                    # Deadline may have been extended by a command pending ACK
                    if deadline > time.monotonic():
                        continue

                    logger.debug("No response to %s", name)
                    raise iAPTimeoutError(f"No response to {name} in time") from None

                if isinstance(item, Exception):
                    raise item

                ack = lingo.parse_ack(item)
                if (
                    ack is not None
                    and ack[1] == command_id
                    and item.command_id not in response_ids
                ):
                    status = ack[0]

                    if status == lingo.ACK_PENDING:
                        deadline = max(deadline, time.monotonic() + self._pending_wait(item))
                        continue

                    if status != lingo.ACK_SUCCESS:
                        logger.debug("%s rejected: %s", name, ack_status_name(status))
                        raise iAPAckError(status, name)

                    return packets

                packets.append(item)
                if done is not None and done(packets):
                    return packets
        finally:
            with self._lock:
                if collector in self._collectors:
                    self._collectors.remove(collector)

    @staticmethod
    def _pending_wait(ack: Packet) -> float:
        """Maximum wait in seconds of a command pending ACK, 0 if it has none"""

        # Command pending ACKs end with the maximum wait in ms
        if len(ack.data) >= 6:
            return int.from_bytes(ack.data[-4:], "big") / 1000.0

        return 0.0

    def _wait(self, pending: _Pending) -> Packet:
        while True:
            remaining = pending.deadline - time.monotonic()

            try:
                return pending.future.result(timeout=max(remaining, 0))
            except FutureTimeoutError:
                # Deadline may have been extended by a command pending ACK
                if pending.deadline > time.monotonic():
                    continue

                logger.debug(
                    "No response to %s.%s",
                    type(pending.lingo).__name__,
                    pending.lingo.command_name(pending.command_id),
                )
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

        log_packet("<-", lingo, packet)

        if lingo is None:
            logger.debug("Ignoring packet of unregistered lingo 0x%02X", packet.lingo_id)
            return

        if self._resolve_pending(lingo, packet) or self._collect(lingo, packet):
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
                    wait = self._pending_wait(packet)
                    if wait:
                        logger.debug(
                            "%s.%s pending, waiting up to %.1f s",
                            type(lingo).__name__,
                            lingo.command_name(pending.command_id),
                            wait,
                        )
                        pending.deadline = max(
                            pending.deadline, time.monotonic() + wait
                        )
                    return True

                if status != lingo.ACK_SUCCESS:
                    logger.debug(
                        "%s.%s rejected: %s",
                        type(lingo).__name__,
                        lingo.command_name(pending.command_id),
                        ack_status_name(status),
                    )
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

    def _collect(self, lingo: Lingo, packet: Packet) -> bool:
        """Pass the packet to the request_multiple() gathering it, returns whether one matched"""

        ack = lingo.parse_ack(packet)

        with self._lock:
            for collector in self._collectors:
                if collector.lingo is not lingo:
                    continue

                if (
                    collector.transaction_id is not None
                    and packet.transaction_id is not None
                    and collector.transaction_id != packet.transaction_id
                ):
                    continue

                if packet.command_id in collector.response_ids or (
                    ack is not None and ack[1] == collector.command_id
                ):
                    collector.packets.put(packet)
                    return True

        return False
