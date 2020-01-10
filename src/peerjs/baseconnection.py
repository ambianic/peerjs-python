"""Base abstractions for peer to peer connections."""
from abc import abstractmethod

from aiortc import RTCPeerConnection
from pyee import AsyncIOEventEmitter

from .enums import ConnectionType
from .servermessage import ServerMessage


class BaseConnection(AsyncIOEventEmitter):
    """Base abstract class for peer to peer connections."""

    @property
    def type() -> ConnectionType:
        """Return connection type."""
        return None

    @property
    def open(self):
        """Return True if this connection is open."""
        return self._open

    def __init__(
        self,
        peer: str = None,
        provider=None,  # provider: Peer
        metadata=None,
        **options
         ):
        """Create connection construct."""
        super().__init__()
        self.peer = peer
        self.provider = provider
        self.metadata = metadata
        self.options = options
        self._open = False
        self.connectionId: str = None
        self.peerConnection: RTCPeerConnection = None

    @abstractmethod
    def close(self) -> None:
        """Close this connection."""

    @abstractmethod
    def handleMessage(self, message: ServerMessage) -> None:
        """Handle incoming message."""
