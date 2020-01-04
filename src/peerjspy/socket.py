"""Convenience class to manage peer websocket connection."""
from pyee import AsyncIOEventEmitter
import logging
from .enums import SocketEventType
import json
import websockets
from websockets import WebSocket, ConnectionClosed
import asyncio

log = logging.getLogger(__name__)


class Socket(AsyncIOEventEmitter):
    """An abstraction on top of WebSockets.

    Provides efficient connection for peers to the signaling server.
    """

    def __init__(
        self,
        secure: bool = True,
        host: str = None,
        port: int = None,
        path: str = None,
        key: str = None,
        pingInterval: int = 5000
    ) -> None:
        """Create new wrapper around websocket."""
        self.super()
        wsProtocol = "wss://" if secure else "ws://"
        self._baseUrl: str = f"{wsProtocol}{host}:{port}{path}peerjs?key={key}"
        self._disconnected: bool = True
        self._id: str = None
        self._messagesQueue: list = []
        self._websocket: WebSocket = None
        self._receiver: asyncio.Task = None

    async def _connect(self, wss_url=None):
        """Connect to WebSockets server."""
        assert wss_url
        # connect to websocket
        websocket = await websockets.connect(wss_url, ssl=True)
        self._sendQueuedMessages()
        log.debug("WebSockets open")
        await websocket.send(
            json.dumps({"ping": "once"})
        )
        self._disconnected = False
        return websocket

    async def _receive(self, websocket=None):
        assert websocket
        try:
            # receive messages until websocket is closed
            async for message in websocket:
                try:
                    data = json.loads(message)
                    log.log("Server message received:", data)
                    self.emit(SocketEventType.Message, data)
                except Exception as e:
                    log.warning("Invalid server message: {}, error {}",
                                message, e)
                await self.emit('message', message)
        except ConnectionClosed:
            log.debug("Websocket connection closed.")
        except RuntimeError as e:
            log.warning("Websocket connection error: {}", e)
        finally:
            # remote peer closed websocket connection
            # or this socket was explicitly closed via close().
            # If its the former case, let's close our end and cleanup.
            if not self._disconnected:
                log.debug("Websocket connection closed")
                await self.close()

    async def start(self, id: str, token: str) -> None:
        """Start socket connection."""
        self._id = id
        _ws_url = f"{self._baseUrl}&id={id}&token={token}"
        if (self._websocket or not self._disconnected):
            # socket already connected
            return
        self._connect(wss_url=_ws_url)
        # ask asyncio to schedule a receiver soon
        # it will end when the socket closes
        self._receiver = asyncio.create_task(
            self._receive(websocket=self._websocket))

    # Is the websocket currently open?
    def _wsOpen(self) -> bool:
        return self._websocket and self._websocket.open

    # Send queued messages.
    def _sendQueuedMessages(self) -> None:
        # Create copy of queue and clear it,
        # because send method push the message back to queue
        # if something goes wrong
        copiedQueue = [*self._messagesQueue]
        self._messagesQueue = []
        for message in copiedQueue:
            self.send(message)

    def send(self, data: any) -> None:
        """Expose send for DC & Peer."""
        # If the socket was already closed, nothing to do
        if self._disconnected:
            return

        # If we didn't get an ID yet,
        # we can't yet send anything so we should queue
        # up these messages.
        if not self._id:
            self._messagesQueue.push(data)
            return
        if not data.type:
            self.emit(SocketEventType.Error, "Invalid message")
            return
        if not self._wsOpen():
            return
        message = json.dumps(data)
        self._websocket.send(message)

    def close(self) -> None:
        """Close socket and stop any pending communication."""
        if not self._disconnected:
            log.debug("Closing socket.")
            self._cleanup()
            self._disconnected = True
            self.emit(SocketEventType.Disconnected)

    def _cleanup(self) -> None:
        if self._websocket:
            self._websocket.close()
            self._websocket = None
