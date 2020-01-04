"""Base abstractions for peer to peer connections."""
from pyee import AsyncIOEventEmitter
from ..peer import Peer
from servermessage import ServerMessage
from enums import ConnectionType
from abc import abstractmethod
from aiortc import RTCPeerConnection


class BaseConnection(AsyncIOEventEmitter):
    """Base abstract class for peer to peer connections."""

    @abstractmethod
    def type() -> ConnectionType:
        """Return connection type."""

    @property
    def open(self):
        """Return True if this connection is open."""
        return self._open

    def __init__(
        self,
        peer: str = None,
        provider: Peer = None,
        options: any = None
         ):
        """Create connection construct."""
        super()
        self.metadata = options.metadata
        self._open = False
        self.connectionId: str = None
        self.peerConnection: RTCPeerConnection = None

    @abstractmethod
    def close(self) -> None:
        """Close this connection."""

    @abstractmethod
    def handleMessage(self, message: ServerMessage) -> None:
        """Handle incoming message."""
