"""Wrapper fro messages from a signaling server."""
from dataclasses import dataclass
from typing import Any, Optional

from dataclasses_json import dataclass_json

from .enums import ServerMessageType


@dataclass_json
@dataclass
class ServerMessage:
    """Wrapper for messages from the signaling server."""

    type: ServerMessageType = None
    payload: Optional[Any] = None
    src: Optional[str] = None
