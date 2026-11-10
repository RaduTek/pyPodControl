from pathlib import Path

from .base import AuthenticationProvider

DEFAULT_CERTIFICATE_PATH = Path(__file__).with_name("apple_auth_cert_2.bin")
"""Certificate shipped with the library, captured from a real authentication"""

DEFAULT_DEVICE_ID = 0x200
"""Device ID that Authentication 2.0 accessories send (from the IDPS sample)"""


class BypassedAuthenticationProvider(AuthenticationProvider):
    """
    ### BypassedAuthenticationProvider

    Authentication for iPods whose signature verifier has been bypassed, so
    that they authenticate an accessory without a Made-for-iPod coprocessor.

    Such a patch (for example RepriseOS on the iPod Classic) forces the
    device-signature check to succeed, so any signature bytes are accepted.
    The iPod still performs a genuine X.509 certificate check, so a real Apple
    certificate must be provided; the library ships one captured from a
    successful authentication.

    This only works on iPods running firmware with the bypass patch. A stock
    iPod rejects the mock signature and refuses the authenticated lingoes.
    """

    def __init__(
        self,
        certificate_path: str | Path = DEFAULT_CERTIFICATE_PATH,
        device_id: int = DEFAULT_DEVICE_ID,
        signature_length: int = 128,
    ) -> None:
        """
        Create a new bypassed authentication provider

        - certificate_path: Path to the X.509 certificate sent to the iPod
        - device_id: Accessory Device ID declared during identification
        - signature_length: Length of the mock signature (any bytes are accepted)
        """

        self.certificate_path = Path(certificate_path)
        self._device_id = device_id
        self.signature_length = signature_length
        self._certificate: bytes | None = None

    @property
    def protocol_version(self) -> tuple[int, int]:
        return (2, 0)

    @property
    def device_id(self) -> int:
        return self._device_id

    def get_certificate(self) -> bytes:
        """Read and cache the certificate sent in RetDevAuthenticationInfo"""

        if self._certificate is None:
            self._certificate = self.certificate_path.read_bytes()

        return self._certificate

    def sign_challenge(self, challenge: bytes) -> bytes:
        """
        Return a mock signature

        A real accessory signs the challenge with its coprocessor here. The
        bypass patch accepts any bytes, so a zero-filled signature is returned.
        """

        return bytes(self.signature_length)
