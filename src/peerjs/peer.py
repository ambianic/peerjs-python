"""Python port of PeerJS client with built in signaling to PeerJS server."""
# import json
# import websockets
# from websockets import WebSocket, ConnectionClosed
import asyncio
import logging
from dataclasses import dataclass
from typing import Any, List
import traceback

from pyee import AsyncIOEventEmitter

from .api import API
from .baseconnection import BaseConnection
from .dataconnection import DataConnection
from .enums import (
    ConnectionType,
    PeerErrorType,
    PeerEventType,
    ServerMessageType,
    SocketEventType,
)
from .servermessage import ServerMessage
from .socket import Socket
from .util import util

log = logging.getLogger(__name__)


@dataclass
class PeerConnectOption:
    """Peer connection configuration options."""

    label: str = None
    metadata: Any = None
    serialization: str = None
    reliable: bool = None


PEER_DEFAULT_KEY = "peerjs"


@dataclass
class PeerOptions:
    """Peer configuration options."""

    host: str = util.CLOUD_HOST
    port: int = util.CLOUD_PORT
    path: str = "/"
    key: str = PEER_DEFAULT_KEY
    token: str = None
    config: Any = util.defaultConfig
    secure: bool = False
    pingInterval: int = 5  # ping to signaling server in seconds


class Peer(AsyncIOEventEmitter):
    """A peer that can initiate direct connections with other peers."""

    def __init__(self,
                 id: str = None,
                 peer_options: PeerOptions = None):
        """Create a peer instance."""
        super().__init__()

        # Configure options
        self._options: PeerOptions = peer_options
        self._api: API = None
        self._socket: Socket = None

        self._id: str = id
        self._lastServerId: str = None

        # States.
        # When True, all peer and server connections have been killed.
        self._destroyed = False
        # When True, connection to PeerServer killed
        # but P2P connections still active.
        self._disconnected = False
        # When True, websocket to signaling server is open.
        self._open = False
        # All direct peer connections from this peer.
        self._connections: dict = {}
        # Messages received from the signaling server
        # waiting to be sent out to remote peers.
        # dic: connectionId => [list of server messages]
        self._lostMessages: dict = {}

        self._id = id

        # Set path correctly.
        if self._options.path:
            if self._options.path[0] != "/":
                self._options.path = "/" + self._options.path
            if self._options.path[len(self._options.path) - 1] != "/":
                self._options.path += "/"

        self._api = API(self._options)

    async def start(self):
        """Activate Peer instance."""
        self._socket = self._createServerConnection()
        # Sanity checks
        # Ensure alphanumeric id
        if self._id and not util.validateId(self._id):
            self._delayedAbort(PeerErrorType.InvalidID,
                               f'ID "{self._id}" is invalid')
            return

        if self._id is None:
            try:
                id = await self._api.retrieveId()
                self._id = id
            except Exception as e:
                await self._abort(PeerErrorType.ServerError, e)
                return
        await self.socket.start(self._id, self._options.token)
        log.info('Peer started with UUID: %s', self._id)

    @property
    def id(self, ) -> None:
        """Return the UUID of this peer."""
        return self._id

    @property
    def options(self, ):
        """Return peer configuration options."""
        return self._options

    @property
    def open(self, ):
        """Return true if this peer connection is open."""
        return self._open

    @property
    def socket(self, ):
        """Return peer's websocket wrapper for the signaling connection."""
        return self._socket

    # #
    #  * @deprecated
    #  * Return type will change from Object to Map<string,[]>
    #  */
    # get connections(): Object {
    #   const plainConnections = Object.create(null);
    #
    #   for (let [k, v] of this._connections) {
    #     plainConnections[k] = v;
    #   }
    #
    #   return plainConnections;
    # }

    @property
    def destroyed(self, ):
        """Return True if peer connections have been destroyed."""
        return self._destroyed

    @property
    def disconnected(self, ):
        """Return True if peer is disconnected from signaling server."""
        return self._disconnected

    def _createServerConnection(self) -> Socket:
        socket = Socket(
            self._options.secure,
            self._options.host,
            self._options.port,
            self._options.path,
            self._options.key,
            self._options.pingInterval)

        @socket.on(SocketEventType.Message)
        async def on_message(data: ServerMessage):
            await self._handleMessage(data)

        @socket.on(SocketEventType.Error)
        async def on_error(error: str):
            await self._abort(PeerErrorType.SocketError, error)

        @socket.on(SocketEventType.Disconnected)
        async def on_disconnected():
            if self.disconnected:
                return
            self.emitError(PeerErrorType.Network, "Lost connection to server.")
            await self.disconnect()

        @socket.on(SocketEventType.Close)
        async def on_close():
            if self.disconnected:
                await self._abort(PeerErrorType.SocketClosed,
                                  "Underlying socket is already closed.")

        return socket

    async def _handleMessage(self, message: ServerMessage) -> None:
        """Handle messages from the server."""
        type = message.type
        peerId = message.src
        payload = message.payload

        log.debug('\n Handling server message \n type %s, '
                  '\n source peer/client id %s, \n message payload %s, '
                  '\n full message %r',
                  type, peerId, payload, message)

        server_messenger = AsyncIOEventEmitter()

        # The connection to the server is open.
        @server_messenger.once(ServerMessageType.Open)
        def _on_server_open():
            self._lastServerId = self.id
            self._open = True
            log.info('Signaling server connection open.')
            self.emit(PeerEventType.Open, self.id)

        # Server error.
        @server_messenger.once(ServerMessageType.Error)
        async def _on_server_error():
            await self._abort(PeerErrorType.ServerError, payload.msg)

        # The selected ID is taken.
        @server_messenger.once(ServerMessageType.IdTaken)
        async def _on_server_idtaken():
            await self._abort(PeerErrorType.UnavailableID,
                              f'ID "${self.id}" is taken')

        # The given API key cannot be found.
        @server_messenger.once(ServerMessageType.InvalidKey)
        async def _on_server_invalidkey():
            await self._abort(PeerErrorType.InvalidKey,
                              f'API KEY "${self._options.key}" is invalid')

        # Another peer has closed its connection to this peer.
        @server_messenger.once(ServerMessageType.Leave)
        async def _on_server_leave():
            log.debug(f'Received leave message from ${peerId}')
            await self._cleanupPeer(peerId)
            self._connections.delete(peerId)

        # The offer sent to a peer has expired without response.
        @server_messenger.once(ServerMessageType.Expire)
        def _on_server_expire():
            self.emitError(PeerErrorType.PeerUnavailable,
                           f'Could not connect to peer ${peerId}')

        # Server relaying offer for a direct connection from a remote peer
        @server_messenger.once(ServerMessageType.Offer)
        async def _on_server_offer():
            await self._handle_offer(peerId, payload)

        # Something went wrong during emit message handling
        # @server_messenger.once('error')
        # def on_error(error_message):
        #     log.error('Error on server message emit: %r', error_message)

        is_handled = server_messenger.emit(type)
        if not is_handled:
            if not payload:
                log.warn(f'You received a malformed message '
                         f'from ${peerId} of type ${type}')
                return
            connectionId = payload['connectionId']
            connection = self.getConnection(peerId, connectionId)
            if connection and connection.peerConnection:
                # Pass it on.
                await connection.handleMessage(message)
            elif connectionId:
                # Store for possible later use
                self._storeMessage(connectionId, message)
            else:
                log.warn("You received an unrecognized message:", message)

    async def _handle_offer(self, peerId=None, payload=None):
        """Handle remote peer offer for a direct connection."""
        # we should consider switching this to CALL/CONNECT,
        # but this is the least breaking option.
        log.debug("\n Remote peer id %s offering connection. \n Payload %s",
                  peerId, payload)
        connectionId = payload['connectionId']
        connection = self.getConnection(peerId, connectionId)

        if (connection):
            connection.close()
            log.warning(f'Offer received for '
                        f'existing Connection ID:${connectionId}')

        # Create a new connection.
        if payload['type'] == ConnectionType.Media.value:
            pass
        # MediaConnection not supported yet in the Python port of PeerJS yet.
        #       Contributions welcome!
        #   connection = new MediaConnection(peerId, this, {
        #     connectionId: connectionId,
        #     _payload: payload,
        #     metadata: payload.metadata
        #   });
        #   this._addConnection(peerId, connection);
        #   this.emit(PeerEventType.Call, connection);
        elif payload['type'] == ConnectionType.Data.value:
            connection = DataConnection(
                peerId=peerId,
                provider=self,
                connectionId=connectionId,
                label=payload['label'],
                serialization=payload['serialization'],
                reliable=payload['reliable'],
                _payload=payload,
                metadata=payload.get('metadata', None)
                )
            await connection.start()
            self._addConnection(peerId, connection)
            self.emit(PeerEventType.Connection, connection)
        else:
            log.warning('Received malformed connection type: %s',
                        payload["type"])
            return

        # Retrieved pending messages from the server for remote peers.
        messages = self._getMessages(connectionId)
        for message in messages:
            await connection.handleMessage(message)

    def _storeMessage(self,
                      connectionId: str, message: ServerMessage) -> None:
        """Store messages without a set up connection, to be claimed later."""
        if connectionId not in self._lostMessages:
            self._lostMessages[connectionId] = []
        message_list = self._lostMessages.get(connectionId)
        message_list.append(message)

    def _getMessages(self, connectionId: str) -> List[ServerMessage]:
        """Retrieve messages from lost message store."""
        messages = self._lostMessages.pop(connectionId, [])
        return messages

    async def connect(self,
                      peer: str,
                      options: PeerConnectOption = {}) -> DataConnection:
        """Return a DataConnection to the specified remote peer.

        See documentation for a complete list of options.
        """
        if self.disconnected:
            log.warning(
                "You cannot connect to a new Peer because you called "
                ".disconnect() on this Peer and "
                "ended your connection with the "
                "server. You can create a new Peer to reconnect, "
                " or call reconnect "
                "on this peer if you believe its ID to still be available."
            )
            self.emitError(
                PeerErrorType.Disconnected,
                "Cannot connect to new Peer after disconnecting from server."
            )
            return

        dataConnection = DataConnection(peer, self, options)
        await dataConnection.start()
        self._addConnection(peer, dataConnection)
        return dataConnection

    # MediaConnection not implemented in Python port yet.
    #           Contributions welcome!
    # /**
    # * Returns a MediaConnection to the specified peer.
    # See documentation for a
    # * complete list of options.
    # */
    # call(peer: string, stream: MediaStream, options: any = {}):
    #    MediaConnection {
    # if (this.disconnected) {
    #   logger.warn(
    #     "You cannot connect to a new Peer because you called " +
    #     ".disconnect() on this Peer and ended your connection with the " +
    #     "server. You can create a new Peer to reconnect."
    #   );
    #   this.emitError(
    #     PeerErrorType.Disconnected,
    #     "Cannot connect to new Peer after disconnecting from server."
    #   );
    #   return;
    # }
    #
    # if (!stream) {
    #   logger.error(
    #     "To call a peer, you must provide a stream from your browser's
    #       `getUserMedia`."
    #   );
    #   return;
    # }
    #
    # options._stream = stream;
    #
    # const mediaConnection = new MediaConnection(peer, this, options);
    # this._addConnection(peer, mediaConnection);
    # return mediaConnection;
    # }

    def _addConnection(self,
                       peerId: str, connection: BaseConnection) -> None:
        """Add a data/media connection to this peer."""
        log.debug(f"add connection ${connection.type}:"
                  f"${connection.connectionId} to peerId:${peerId}")
        if peerId not in self._connections:
            self._connections[peerId] = []
        self._connections[peerId].append(connection)

    def _removeConnection(self, connection: BaseConnection) -> None:
        connections = self._connections.get(connection.peer, None)
        if connections:
            try:
                connections.remove(connection)
            except ValueError as err:
                log.warning('Error removing connection peer id %s. '
                            'Connection not found in managed connections list.'
                            '\n%r',
                            connection.peer, err)
        # remove from lost messages
        self._lostMessages.pop(connection.connectionId, None)

    def getConnection(self,
                      peerId: str,
                      connectionId: str) -> BaseConnection:
        """Retrieve a data/media connection for this peer."""
        connections = self._connections.get(peerId, None)
        if not connections:
            return None
        for connection in connections:
            if connection.connectionId == connectionId:
                return connection
        return None

    async def _delayedAbort(self, type: PeerErrorType, message: str) -> None:
        asyncio.asyncio.create_task(self._abort(type, message))

    async def _abort(self, type: PeerErrorType, message: str) -> None:
        """Emit an error message and destroy the Peer.

        The Peer is not destroyed if it's in a disconnected state,
        in which case
        it retains its disconnected state and its existing connections.
        """
        log.error('Aborting! \n'
                  'PeerErrorType: %s \n'
                  'Error message: %s',
                  type,
                  message)
        traceback.print_stack()
        self.emitError(type, message)
        if not self._lastServerId:
            await self.destroy()
        else:
            await self.disconnect()

    def emitError(self, type: PeerErrorType, err: str) -> None:
        """Emit a typed error message."""
        log.warning('Connection error: %s', err)
        if isinstance(err, str):
            err = RuntimeError(err)
        else:
            assert isinstance(err, Exception)
        log.warning('Connection error: \n%s', err)
        err.type = type
        self.emit(PeerEventType.Error, err)

    async def destroy(self) -> None:
        """Destroy Peer and close all active connections.

        Close all active peer connections and the active server connection.
        Warning: The peer can no longer create or
        accept connections after being
        destroyed.
        """
        if self.destroyed:
            return
        log.debug(f'Destroy peer with ID:${self.id}')
        await self.disconnect()
        await self._cleanup()
        self._destroyed = True
        self.emit(PeerEventType.Close)

    async def _cleanup(self) -> None:
        """Disconnects every connection on this peer."""
        # we need to iterate over a copy
        # in order to remove elements from the original dict
        keys_copy = list(self._connections.keys())
        for peerId in keys_copy:
            await self._cleanupPeer(peerId)
            self._connections.pop(peerId, None)
        self.socket.remove_all_listeners()

    async def _cleanupPeer(self, peerId: str) -> None:
        """Close all connections to this peer."""
        connections = self._connections.get(peerId)
        if not connections:
            return
        for connection in connections:
            await connection.close()

    async def disconnect(self) -> None:
        """Disconnects the Peer's connection to the PeerServer.

        Does not close any active connections.
        Warning: The peer can no longer create or
        accept connections after being
        disconnected. It also cannot reconnect to the server.
        """
        if self.disconnected:
            return
        currentId = self.id
        log.debug(f'Disconnect peer with ID:${currentId}')
        self._disconnected = True
        self._open = False
        if (self.socket is not None):
            await self.socket.close()
        self._lastServerId = currentId
        self._id = None
        self.emit(PeerEventType.Disconnected, currentId)

    async def reconnect(self) -> None:
        """Attempt to reconnect with the same ID."""
        if self.disconnected and not self.destroyed:
            log.debug("Attempting reconnection "
                      f"to server with ID {self._lastServerId}")
            self._disconnected = False
            self._id = self._lastServerId
            await self.start()
        elif self.destroyed:
            raise RuntimeError("This peer cannot reconnect to the server. "
                               "It has already been destroyed.")
        elif not self.disconnected and not self.open:
            # Do nothing. We're still connecting for the first time.
            log.info("In a hurry? "
                     "We're still trying to make the initial connection!")
        else:
            raise RuntimeError(
                f"Peer ${self.id} cannot reconnect "
                "because it is not disconnected from the server!")
