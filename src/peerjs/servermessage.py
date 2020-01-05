"""Wrapper fro messages from a signaling server."""
from .enums import ServerMessageType


class ServerMessage:
    """Wrapper fro messages from a signaling server."""

    def __init__(self):
        """Create server message constructs."""
        self.type: ServerMessageType = None
        self.payload = None
        self.src: str = None
