import logging
import threading
from abc import ABC, abstractmethod
from typing import Callable

from ..errors import TransportError
from ..packet import MAX_PAYLOAD, PacketParser, encode_frame

logger = logging.getLogger(__name__)

Receiver = Callable[[bytes], None]
"""Callback invoked with the payload of every received packet"""


class Transport(ABC):
    """
    ### Transport

    Base class for an iAP transport link

    Handles packet framing and runs a reader thread which passes received
    packet payloads to the receiver callback. Subclasses implement the raw
    I/O for a specific link (UART, USB HID).
    """

    parser: PacketParser
    """Parser for the received byte stream"""

    max_payload_size: int = MAX_PAYLOAD
    """Maximum payload size supported by this transport"""

    def __init__(self) -> None:
        self.parser = PacketParser()
        self._receiver: Receiver | None = None
        self._write_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._running = threading.Event()
        self._closed = threading.Event()
        self._closed.set()

    @property
    def is_open(self) -> bool:
        """Whether the transport is open"""

        return self._running.is_set()

    def set_receiver(self, receiver: Receiver | None) -> None:
        """Set the callback that receives packet payloads"""

        self._receiver = receiver

    def open(self) -> None:
        """Open the transport and start the reader thread"""

        if self.is_open:
            return

        self._open()
        self.parser.reset()
        self._closed.clear()
        self._running.set()

        self._reader = threading.Thread(
            target=self._read_loop, name=f"{type(self).__name__}-reader", daemon=True
        )
        self._reader.start()

    def close(self) -> None:
        """Stop the reader thread and close the transport"""

        if not self.is_open:
            return

        self._running.clear()

        if self._reader is not None and self._reader is not threading.current_thread():
            self._reader.join()
        self._reader = None

        try:
            self._close()
        finally:
            self._closed.set()

    def wait_closed(self, timeout: float | None = None) -> bool:
        """
        Wait until the transport is closed, by close() or because the link
        failed (e.g. the iPod was unplugged), returns whether it is closed
        """

        return self._closed.wait(timeout)

    def wake(self) -> None:
        """Wake up a sleeping iPod, if the transport needs it"""

    def send(self, payload: bytes) -> None:
        """Send a packet with the given payload"""

        if not self.is_open:
            raise TransportError("Transport is not open")

        if len(payload) > self.max_payload_size:
            raise ValueError(
                f"Payload of {len(payload)} bytes exceeds transport maximum of {self.max_payload_size}"
            )

        frame = encode_frame(payload)

        with self._write_lock:
            self._write_frame(frame)

    def __enter__(self) -> "Transport":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _read_loop(self) -> None:
        """Reader thread, feeds received bytes to the parser"""

        while self._running.is_set():
            try:
                chunk = self._read_chunk()
            except Exception:
                if self._running.is_set():
                    # The link failed on its own (e.g. the iPod was unplugged);
                    # release it so the handle does not linger until close()
                    logger.exception("Transport read failed, stopping reader")
                    self._running.clear()
                    self._safe_close()
                    self._closed.set()
                break

            if not chunk:
                continue

            for payload in self.parser.feed(chunk):
                self._deliver(payload)

    def _safe_close(self) -> None:
        """Close the underlying link, ignoring errors"""

        try:
            self._close()
        except Exception:
            logger.debug("Error closing transport", exc_info=True)

    def _deliver(self, payload: bytes) -> None:
        """Pass a received payload to the receiver"""

        if self._receiver is None:
            logger.debug("No receiver, dropping payload %s", payload.hex(" "))
            return

        try:
            self._receiver(payload)
        except Exception:
            logger.exception("Receiver failed handling payload %s", payload.hex(" "))

    @abstractmethod
    def _open(self) -> None:
        """Open the underlying link"""

    @abstractmethod
    def _close(self) -> None:
        """Close the underlying link"""

    @abstractmethod
    def _read_chunk(self) -> bytes:
        """Read available bytes, returning b"" after a short timeout"""

    @abstractmethod
    def _write_frame(self, frame: bytes) -> None:
        """Write an encoded packet frame (start byte to checksum)"""
