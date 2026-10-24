from abc import ABC, abstractmethod


class AuthenticationProvider(ABC):
    """
    ### AuthenticationProvider

    Base class for accessory authentication (Authentication 2.0)

    Provides the accessory certificate and signs the challenges sent by the
    iPod. Implementations may use an Apple Authentication Coprocessor, or
    other sources of the certificate and signature.
    """

    @property
    @abstractmethod
    def protocol_version(self) -> tuple[int, int]:
        """Authentication protocol version (major, minor), e.g. (2, 0)"""

    @abstractmethod
    def get_certificate(self) -> bytes:
        """Accessory certificate data, sent in RetDevAuthenticationInfo"""

    @abstractmethod
    def sign_challenge(self, challenge: bytes) -> bytes:
        """Sign a challenge from GetDevAuthenticationSignature, sent in RetDevAuthenticationSignature"""
