"""Python port of PeerJS client with built in signaling to PeerJS server."""
from typing import List
from pyee import AsyncIOEventEmitter
import logging
from .enums import \
    ConnectionType, \
    PeerErrorType, \
    PeerEventType, \
    SocketEventType, \
    ServerMessageType
import json
import websockets
from websockets import WebSocket, ConnectionClosed
import asyncio
from .socket import Socket
from .dataconnection import DataConnection
from .baseconnection import BaseConnection
from .servermessage import ServerMessage
from .api import API

log = logging.getLogger(__name__)


class PeerConnectOption:
    def __init__(self, **kwargs):
        self.label: str = None
        self.metadata = None
        self.serialization: str = None
        self.reliable: bool = None


class PeerOptions:
    def __init__(self, **kwargs):
        self.debug: int = 0  # 1: Errors, 2: Warnings, 3: All logs
        self.host: str = util.CLOUD_HOST
        self.port: int = util.CLOUD_PORT
        self.path: str = "/"
        self.key: str = Peer.DEFAULT_KEY
        self.token: str = util.randomToken()
        self.config = util.defaultConfig
        self.secure: bool = None
        for k, v in kwargs:
            setattr(self, k, v)


# 0: None, 1: Errors, 2: Warnings, 3: All logs
DEBUG_LEVELS = {
    0: logging.CRITICAL,
    1: logging.ERROR,
    2: logging.WARNING,
    3:  logging.DEBUG
}


def _object_from_string(message_str):
    message = json.loads(message_str)
    if message["type"] in ["answer", "offer"]:
        return RTCSessionDescription(**message)
    elif message["type"] == "candidate":
        candidate = candidate_from_sdp(message["candidate"].split(":", 1)[1])
        candidate.sdpMid = message["id"]
        candidate.sdpMLineIndex = message["label"]
        return candidate


def _object_to_string(obj):
    if isinstance(obj, RTCSessionDescription):
        message = {"sdp": obj.sdp, "type": obj.type}
    elif isinstance(obj, RTCIceCandidate):
        message = {
            "candidate": "candidate:" + candidate_to_sdp(obj),
            "id": obj.sdpMid,
            "label": obj.sdpMLineIndex,
            "type": "candidate",
        }
    else:
        message = {"type": "bye"}
    return json.dumps(message, sort_keys=True)


class Peer(AsyncIOEventEmitter):
    """A peer that can initiate direct connections with other peers."""

    def __init__(self, id: str = None, **options):
        super()

        self._DEFAULT_KEY = "peerjs"

        self._options: PeerOptions
        self._api: API
        self._socket: Socket

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

        userId: str = None

        # Deal with overloading
        if id:
            userId = id

        # Configure options
        this._options = PeerOptions(**options)

        # Set path correctly.
        if self._options.path:
            if self._options.path[0] != "/":
                self._options.path = "/" + this._options.path
            if self._options.path[this._options.path.length - 1] != "/":
                self._options.path += "/"

        self.debug: int = 0  # 1: Errors, 2: Warnings, 3: All logs

        if 0 <= self._options.debug <= 3:
            log.setLevel(DEBUG_LEVELS[self._options.debug])
        else:
            log.warning('Debug level option specified as {} '
                        'which is outside the allowed 0-3 range.'
                        'Setting to lowest log level: 0', self._options.debug)

        self._api = API(**options)
        self._socket = self._createServerConnection()

        # Sanity checks
        # Ensure alphanumeric id
        if userId and not util.validateId(userId):
            self._delayedAbort(PeerErrorType.InvalidID,
                               f'ID "${userId}" is invalid')
            return

        if userId:
            self._initialize(userId)
        else:
            try:
                id = await self._api.retrieveId()
                self._initialize(id)
            except Exception as e:
                self._abort(PeerErrorType.ServerError, e)

    @property
    def id(self, ) -> None:
        return self._id

    @property
    def options(self, ):
        return self._options

    @property
    def open(self, ):
        return self._open

    @property
    def socket(self, ):
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
        return self._destroyed

    @property
    def disconnected(self, ):
        return self._disconnected

    @property
    def _createServerConnection(self, ) -> Socket:
        socket = Socket(
            self._options.secure,
            self._options.host,
            self._options.port,
            self._options.path,
            self._options.key,
            self._options.pingInterval)

        @socket.on(SocketEventType.Message)
        def on_message(data: ServerMessage):
            self._handleMessage(data)

        @socket.on(SocketEventType.Error)
        def on_error(error: str):
            self._abort(PeerErrorType.SocketError, error)

        @socket.on(SocketEventType.Disconnected)
        def on_disconnected():
            if self.disconnected:
                return
            self.emitError(PeerErrorType.Network, "Lost connection to server.")
            self.disconnect()

        @socket.on(SocketEventType.Close)
        def on_close():
            if not this.disconnected:
                self._abort(PeerErrorType.SocketClosed,
                            "Underlying socket is already closed.")

        return socket

    def _initialize(self, id: str) -> None:
        """ Initialize a connection with the server."""
        self._id = id
        self.socket.start(id, self._options.token)

    def _handleMessage(self, message: ServerMessage) -> None:
        """Handles messages from the server."""
        type = message.type
        payload = message.payload
        peerId = message.src

        server_messenger = AsyncIOEventEmitter()

        # The connection to the server is open.
        @server_messenger.on(ServerMessageType.Open)
        def _on_server_open(peerId=None, payload=None):
            self._lastServerId = self.id
            self._open = True
            self.emit(PeerEventType.Open, this.id)

        # Server error.
        @server_messenger.on(ServerMessageType.Error)
        def _on_server_error(peerId=None, payload=None):
            self._abort(PeerErrorType.ServerError, payload.msg)

        # The selected ID is taken.
        @server_messenger.on(ServerMessageType.IdTaken)
        def _on_server_idtaken(peerId=None, payload=None):
            self._abort(PeerErrorType.UnavailableID,
                        f'ID "${this.id}" is taken')

        # The given API key cannot be found.
        @server_messenger.on(ServerMessageType.InvalidKey)
        def _on_server_invalidkey(peerId=None, payload=None):
            self._abort(PeerErrorType.InvalidKey,
                        f'API KEY "${this._options.key}" is invalid')

        # Another peer has closed its connection to this peer.
        @server_messenger.on(ServerMessageType.Leave)
        def _on_server_leave(peerId=None, payload=None):
            log.debug(f'Received leave message from ${peerId}')
            self._cleanupPeer(peerId)
            self._connections.delete(peerId)

        # The offer sent to a peer has expired without response.
        @server_messenger.on(ServerMessageType.Expire)
        def _on_server_expire(peerId=None, payload=None):
            self.emitError(PeerErrorType.PeerUnavailable,
                           f'Could not connect to peer ${peerId}')

        # Server relaying offer for a direct connection from a remote peer
        @server_messenger.on(ServerMessageType.Offer)
        def _on_server_offer(peerId=None, payload=None):
            self._handle_offer(peerId, payload)

        # Something went wrong during emit message handling
        @server_messenger.on('error')
        def on_error(error_message):
            log.warning('Error on server message emit: {}', message)

        is_handled = server_messenger.emit(type,
                                           peerId=peerId,
                                           payload=payload)
        if not is_handled:
            _handle_other(peerId=peerId, payload=payload)

    def _handle_other(self, peerId=None, payload=None):
        if not payload:
            log.warn(f'You received a malformed message '
                     f'from ${peerId} of type ${type}')
            return
        connectionId = payload.connectionId
        connection = self.getConnection(peerId, connectionId)
        if connection and connection.peerConnection:
            # Pass it on.
            connection.handleMessage(message)
        elif connectionId:
            # Store for possible later use
            self._storeMessage(connectionId, message)
        else:
            log.warn("You received an unrecognized message:", message)

    def _handle_offer(self, peerId=None, payload=None):
        """Handles remote peer offer for a direct connection."""
        # we should consider switching this to CALL/CONNECT,
        # but this is the least breaking option.
        connectionId = payload.connectionId
        connection = self.getConnection(peerId, connectionId)

        if (connection):
            connection.close()
            logger.warn(f'Offer received for '
                        f'existing Connection ID:${connectionId}')

        # Create a new connection.
        if payload.type == ConnectionType.Media:
            pass
        # MediaConnection not supported in the Python port of PeerJS yet.
        #       Contributions welcome!
        #   connection = new MediaConnection(peerId, this, {
        #     connectionId: connectionId,
        #     _payload: payload,
        #     metadata: payload.metadata
        #   });
        #   this._addConnection(peerId, connection);
        #   this.emit(PeerEventType.Call, connection);
        elif payload.type == ConnectionType.Data:
            connection = DataConnection(
                peerId,
                self,
                connectionId=connectionId,
                _payload=payload,
                metadata=payload.metadata,
                label=payload.label,
                serialization=payload.serialization,
                reliable=payload.reliable)
            self._addConnection(peerId, connection)
            self.emit(PeerEventType.Connection, connection)
        else:
            logger.warn(f'Received malformed connection type:${payload.type}')
            return

        # Retrieved pending messages from the server for remote peers.
        messages = self._getMessages(connectionId)
        for message in messages:
            connection.handleMessage(message)

    def _storeMessage(self,
                      connectionId: string, message: ServerMessage) -> None:
        """Stores messages without a set up connection, to be claimed later."""
        if not this._lostMessages.has(connectionId):
            self._lostMessages.set(connectionId, [])

        message_list = self._lostMessages.get(connectionId)
        message_list.append(message)

    def _getMessages(self, connectionId: string) -> List[ServerMessage]:
        """Retrieve messages from lost message store."""
        messages = self._lostMessages.pop(connectionId, [])
        return messages

    def connect(self,
                peer: string,
                options: PeerConnectOption = {}) -> DataConnection:
        """Return a DataConnection to the specified peer.

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

        dataConnection = DataConnection(peer, this, options)
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
                       peerId: string, connection: BaseConnection) -> None:
        """Add a data/media connection to this peer."""
        log.debug(f"add connection ${connection.type}:"
                  f"${connection.connectionId} to peerId:${peerId}")
        if not this._connections.has(peerId):
            self._connections.set(peerId, [])
        self._connections.get(peerId).push(connection)

    def _removeConnection(self, connection: BaseConnection) -> None:
        connections = this._connections.get(connection.peer, None)
        if connections:
            connections.pop(connection, None)
        # remove from lost messages
        this._lostMessages.pop(connection.connectionId, None)

    def getConnection(self,
                      peerId: string,
                      connectionId: string) -> BaseConnection:
        """Retrieve a data/media connection for this peer."""
        connections = this._connections.get(peerId, None)
        if not connections:
            return None
        for connection in connections:
            if connection.connectionId == connectionId:
                return connection
        return None

    async def _delayedAbort(self, type: PeerErrorType, message: str) -> None:
        asyncio.asyncio.create_task(self._abort(type, message))

    async def _abort(self, type: PeerErrorType, message: str) -> None:
        """Emits an error message and destroys the Peer.

        The Peer is not destroyed if it's in a disconnected state,
        in which case
        it retains its disconnected state and its existing connections.
        """
        log.error("Aborting!")
        self.emitError(type, message)
        if not self._lastServerId:
            self.destroy()
        else:
            self.disconnect()

    def emitError(type: PeerErrorType, err: str) -> None:
        """Emit a typed error message."""
        log.error("Error:", err)
        if isinstance(err, str):
            error = Error(err)
        else:
            assert isinstance(error, Error)
        error.type = type
        self.emit(PeerEventType.Error, error)

    def destroy() -> None:
        """Destroy the Peer: close all active connections.

         Close all active peer connections and the active server connection.
         Warning: The peer can no longer create or
         accept connections after being
         destroyed.
         """
        if self.destroyed:
            return
        log.debug(f'Destroy peer with ID:${this.id}')
        self.disconnect()
        self._cleanup()
        self._destroyed = True
        self.emit(PeerEventType.Close)

    def _cleanup() -> None:
        """Disconnects every connection on this peer."""
        for peerId in self._connections.keys():
            self._cleanupPeer(peerId)
            self._connections.delete(peerId)
            self.socket.removeAllListeners()

    def _cleanupPeer(peerId: string) -> None:
        """Closes all connections to this peer."""
        connections = this._connections.get(peerId)
        if not connections:
            return
        for connection in connections:
            connection.close()

    def disconnect() -> None:
        """Disconnects the Peer's connection to the PeerServer.

        Does not close any active connections.
        Warning: The peer can no longer create or
        accept connections after being
        disconnected. It also cannot reconnect to the server.
        """
        if self.disconnected:
            return
        currentId = this.id
        log.debug(f'Disconnect peer with ID:${currentId}')
        self._disconnected = True
        self._open = False
        self.socket.close()
        self._lastServerId = currentId
        self._id = None
        self.emit(PeerEventType.Disconnected, currentId)

    def reconnect() -> None:
        """Attempts to reconnect with the same ID."""
        if self.disconnected and not self.destroyed:
            log.debug(f"Attempting reconnection "
                      "to server with ID ${this._lastServerId}")
            self._disconnected = False
            self._initialize(this._lastServerId)
        elif this.destroyed:
            raise RuntimeError("This peer cannot reconnect to the server. "
                               "It has already been destroyed.")
        elif not self.disconnected and not self.open:
            # Do nothing. We're still connecting for the first time.
            log.info("In a hurry? "
                     "We're still trying to make the initial connection!")
        else:
            raise RuntimeError(
                f"Peer ${this.id} cannot reconnect "
                "because it is not disconnected from the server!")

    async def listAllPeers() -> []:
        """Get a list of available peer IDs.

        WARNING: Unintended access to this method is a potential security
        risk as it would enable malicious clients to offer connection
        to all peers connected to the signaling server!

        If you're running your own server, you'll
        want to set allow_discovery: true in the PeerServer options and enforce
        a crypto safe access key.

        If you're using the PeerJS cloud server,
        email team@peerjs.com to get the functionality enabled for
        your key.
        """
        peers = await self._api.listAllPeers()
        return peers
