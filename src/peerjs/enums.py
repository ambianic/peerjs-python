"""Shared Peer enum types."""
from enum import Enum, unique


@unique
class ConnectionEventType(Enum):
    """Connection event types."""

    Open = "Open"
    Stream = "Stream"
    Data = "Data"
    Close = "Close"
    Error = "Error"
    IceStateChanged = "iceStateChanged"


@unique
class ConnectionType(Enum):
    """Connection type."""

    Data = "data"
    Media = "media"


@unique
class PeerEventType(Enum):
    """Peer event type."""

    Open = "Open"
    Close = "Close"
    Connection = "connection"
    Call = "Call"
    Disconnected = "disconnected"
    Error = "Error"


@unique
class PeerErrorType(Enum):
    """Peer error type."""

    BrowserIncompatible = "browser-incompatible"
    Disconnected = "disconnected"
    InvalidID = "invalid-id"
    InvalidKey = "invalid-key"
    Network = "network"
    PeerUnavailable = "peer-unavailable"
    SslUnavailable = "ssl-unavailable"
    ServerError = "server-error"
    SocketError = "socket-error"
    SocketClosed = "socket-closed"
    UnavailableID = "unavailable-id"
    WebRTC = "webrtc"


class SerializationType:
    """Serialization type."""

    # Binary and BinaryUTF8 use message packing
    Binary = "binary"
    BinaryUTF8 = "binary-utf8"

    # JSON type is automatically converted to/from objects
    JSON = "json"

    # Raw is passed without any modifications
    Raw = 'raw'


@unique
class SocketEventType(Enum):
    """Socket event type."""

    Message = "Message"
    Disconnected = "Disconnected"
    Error = "Error"
    Close = "Close"


@unique
class ServerMessageType(Enum):
    """Server Message Type."""

    Heartbeat = "HEARTBEAT"
    Candidate = "CANDIDATE"
    Offer = "OFFER"
    Answer = "ANSWER"
    Open = "OPEN"  # The connection to the server is open.
    Error = "ERROR"  # Server error.
    IdTaken = "ID-TAKEN"  # The selected ID is taken.
    InvalidKey = "INVALID-KEY"  # The given API key cannot be found.
    Leave = "LEAVE"  # Another peer has closed its connection to this peer.
    Expire = "EXPIRE"  # The offer sent to a peer has expired without response.
