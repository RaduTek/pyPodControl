import queue

from pypodcontrol.packet import encode_frame
from pypodcontrol.transport import Transport


class FakeTransport(Transport):
    """In-memory transport, records sent payloads and injects received ones"""

    def __init__(self) -> None:
        super().__init__()
        self.sent: queue.Queue[bytes] = queue.Queue()
        self.incoming: queue.Queue[bytes] = queue.Queue()
        self.on_send = None

    def inject(self, payload: bytes) -> None:
        """Simulate the iPod sending a packet"""

        self.incoming.put(b"\xff" + encode_frame(payload))

    def next_sent(self, timeout: float = 1.0) -> bytes:
        """Payload of the next packet sent by the accessory"""

        return self.sent.get(timeout=timeout)

    def _open(self) -> None:
        pass

    def _close(self) -> None:
        pass

    def _read_chunk(self) -> bytes:
        try:
            return self.incoming.get(timeout=0.02)
        except queue.Empty:
            return b""

    def _write_frame(self, frame: bytes) -> None:
        payload = self.parser.__class__().feed(frame)[0]
        self.sent.put(payload)
        if self.on_send is not None:
            self.on_send(payload)
