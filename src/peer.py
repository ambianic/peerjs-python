"""Python port of PeerJS client with built in signaling to PeerJS server."""
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
from .lib.socket import Socket
from .lib.dataconnection import DataConnection
from .lib.baseconnection import BaseConnection
from .lib.servermessage import ServerMessage
from .lib.rest_api import API

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
    """A peer that can initiate direct connections with multiple other peers."""

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
        # When True, connection to PeerServer killed but P2P connections still active.
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

    log.setLevel()

    if 0 <= self._options.debug <= 3:
        log.setLevel(DEBUG_LEVELS[self._options.debug])

    self._api = API(**options)
    self._socket = self._createServerConnection()

    # Sanity checks
    # Ensure alphanumeric id
    if userId and not util.validateId(userId):
      self._delayedAbort(PeerErrorType.InvalidID, f'ID "${userId}" is invalid')
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
    def id() -> None:
        return self._id

    @property
    def options():
        return self._options

    @property
    def open():
        return self._open

    @property
    def socket():
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
    def destroyed():
        return self._destroyed

    @property
    def disconnected():
        return self._disconnected

    @property
    def _createServerConnection() -> Socket:
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

            self.emitError(PeerErrorType.Network, "Lost connection to server.");
            self.disconnect()

        @socket.on(SocketEventType.Close)
        on_close():
            if not this.disconnected:
                self._abort(PeerErrorType.SocketClosed, "Underlying socket is already closed.")

        return socket

    def _initialize(id: str) -> None:
        """ Initialize a connection with the server."""
        self._id = id
        self.socket.start(id, self._options.token)

    def _handleMessage(message: ServerMessage) -> None:
        """Handles messages from the server."""
        type = message.type
        payload = message.payload
        peerId = message.src

        server_messenger = AsyncIOEventEmitter()

        # The connection to the server is open.
        @server_messenger.on(ServerMessageType.Open)
        def _on_server_open(peerId = None, payload = None):
            self._lastServerId = self.id
            self._open = True
            self.emit(PeerEventType.Open, this.id)

        # Server error.
        @server_messenger.on(ServerMessageType.Error)
        def _on_server_error(peerId = None, payload = None):
            self._abort(PeerErrorType.ServerError, payload.msg)

        # The selected ID is taken.
        @server_messenger.on(ServerMessageType.IdTaken)
        def _on_server_idtaken(peerId = None, payload = None):
            self._abort(PeerErrorType.UnavailableID, f`ID "${this.id}" is taken`)

        # The given API key cannot be found.
        @server_messenger.on(ServerMessageType.InvalidKey)
        def _on_server_invalidkey(peerId = None, payload = None):
            self._abort(PeerErrorType.InvalidKey, f'API KEY "${this._options.key}" is invalid')

        # Another peer has closed its connection to this peer.
        @server_messenger.on(ServerMessageType.Leave)
        def _on_server_leave(peerId = None, payload = None):
            log.debug(f'Received leave message from ${peerId}')
            self._cleanupPeer(peerId)
            self._connections.delete(peerId)

        # The offer sent to a peer has expired without response.
        @server_messenger.on(ServerMessageType.Expire)
        def _on_server_expire(peerId = None, payload = None):
            self.emitError(PeerErrorType.PeerUnavailable, f'Could not connect to peer ${peerId}')

        # Server relaying offer for a direct connection from a remote peer
        @server_messenger.on(ServerMessageType.Offer)
        def _on_server_offer(peerId = None, payload = None):
            self._handle_offer(peerId, payload)

        # Something went wrong during emit message handling
        @server_messenger.on('error')
        def on_error(message):
            log.warning(message)


        is_handled = server_messenger.emit(type, peerId = peerId, payload = payload)
        if not is_handled:
            if not payload:
              log.warn(f'You received a malformed message from ${peerId} of type ${type}')
              return

            connectionId = payload.connectionId
            connection = self.getConnection(peerId, connectionId)

            if connection and connection.peerConnection:
              # Pass it on.
              connection.handleMessage(message)
            elif:
              # Store for possible later use
              self._storeMessage(connectionId, message);
            else:
              log.warn("You received an unrecognized message:", message)


    def _handle_offer(peerId, payload):
        """Handles remote peer offer for a direct connection."""
        # we should consider switching this to CALL/CONNECT,
        # but this is the least breaking option.
        connectionId = payload.connectionId
        connection = self.getConnection(peerId, connectionId)

        if (connection):
            connection.close()
            logger.warn(f'Offer received for existing Connection ID:${connectionId}')

        # Create a new connection.
        if payload.type == ConnectionType.Media:
        # MediaConnection not supported in the Python port of PeerJS yet.
        #       Contributions welcome!
            pass
        #   connection = new MediaConnection(peerId, this, {
        #     connectionId: connectionId,
        #     _payload: payload,
        #     metadata: payload.metadata
        #   });
        #   this._addConnection(peerId, connection);
        #   this.emit(PeerEventType.Call, connection);
        elif payload.type == ConnectionType.Data:
            connection = DataConnection(peerId, self,
                connectionId = connectionId,
                _payload = payload,
                metadata = payload.metadata,
                label = payload.label,
                serialization = payload.serialization,
                reliable = payload.reliable)
            self._addConnection(peerId, connection)
            self.emit(PeerEventType.Connection, connection)
        else:
          logger.warn(f'Received malformed connection type:${payload.type}')
          return

        # Find messages.
        const messages = self._getMessages(connectionId)
        for message in messages:
          connection.handleMessage(message)


    def _storeMessage(connectionId: string, message: ServerMessage) -> None:
        """Stores messages without a set up connection, to be claimed later."""
        if (!this._lostMessages.has(connectionId)) {
          this._lostMessages.set(connectionId, []);
        }

        this._lostMessages.get(connectionId).push(message);
        }

        /** Retrieve messages from lost message store */
        //TODO Change it to private
        public _getMessages(connectionId: string): ServerMessage[] {
        const messages = this._lostMessages.get(connectionId);

        if (messages) {
          this._lostMessages.delete(connectionId);
          return messages;
        }

        return [];
        }

    /**
    * Returns a DataConnection to the specified peer. See documentation for a
    * complete list of options.
    */
    connect(peer: string, options: PeerConnectOption = {}): DataConnection {
    if (this.disconnected) {
      logger.warn(
        "You cannot connect to a new Peer because you called " +
        ".disconnect() on this Peer and ended your connection with the " +
        "server. You can create a new Peer to reconnect, or call reconnect " +
        "on this peer if you believe its ID to still be available."
      );
      this.emitError(
        PeerErrorType.Disconnected,
        "Cannot connect to new Peer after disconnecting from server."
      );
      return;
    }

    const dataConnection = new DataConnection(peer, this, options);
    this._addConnection(peer, dataConnection);
    return dataConnection;
    }

    /**
    * Returns a MediaConnection to the specified peer. See documentation for a
    * complete list of options.
    */
    call(peer: string, stream: MediaStream, options: any = {}): MediaConnection {
    if (this.disconnected) {
      logger.warn(
        "You cannot connect to a new Peer because you called " +
        ".disconnect() on this Peer and ended your connection with the " +
        "server. You can create a new Peer to reconnect."
      );
      this.emitError(
        PeerErrorType.Disconnected,
        "Cannot connect to new Peer after disconnecting from server."
      );
      return;
    }

    if (!stream) {
      logger.error(
        "To call a peer, you must provide a stream from your browser's `getUserMedia`."
      );
      return;
    }

    options._stream = stream;

    const mediaConnection = new MediaConnection(peer, this, options);
    this._addConnection(peer, mediaConnection);
    return mediaConnection;
    }

    /** Add a data/media connection to this peer. */
    private _addConnection(peerId: string, connection: BaseConnection): void {
    logger.log(`add connection ${connection.type}:${connection.connectionId} to peerId:${peerId}`);

    if (!this._connections.has(peerId)) {
      this._connections.set(peerId, []);
    }
    this._connections.get(peerId).push(connection);
    }

    //TODO should be private
    _removeConnection(connection: BaseConnection): void {
    const connections = this._connections.get(connection.peer);

    if (connections) {
      const index = connections.indexOf(connection);

      if (index !== -1) {
        connections.splice(index, 1);
      }
    }

    //remove from lost messages
    this._lostMessages.delete(connection.connectionId);
    }

    /** Retrieve a data/media connection for this peer. */
    getConnection(peerId: string, connectionId: string): null | BaseConnection {
    const connections = this._connections.get(peerId);
    if (!connections) {
      return null;
    }

    for (let connection of connections) {
      if (connection.connectionId === connectionId) {
        return connection;
      }
    }

    return null;
    }

    private _delayedAbort(type: PeerErrorType, message: string | Error): void {
    setTimeout(() => {
      this._abort(type, message);
    }, 0);
    }

    /**
    * Emits an error message and destroys the Peer.
    * The Peer is not destroyed if it's in a disconnected state, in which case
    * it retains its disconnected state and its existing connections.
    */
    private _abort(type: PeerErrorType, message: string | Error): void {
    logger.error("Aborting!");

    this.emitError(type, message);

    if (!this._lastServerId) {
      this.destroy();
    } else {
      this.disconnect();
    }
    }

    /** Emits a typed error message. */
    emitError(type: PeerErrorType, err: string | Error): void {
    logger.error("Error:", err);

    let error: Error & { type?: PeerErrorType };

    if (typeof err === "string") {
      error = new Error(err);
    } else {
      error = err as Error;
    }

    error.type = type;

    this.emit(PeerEventType.Error, error);
    }

    /**
    * Destroys the Peer: closes all active connections as well as the connection
    *  to the server.
    * Warning: The peer can no longer create or accept connections after being
    *  destroyed.
    */
    destroy(): void {
    if (this.destroyed) {
      return;
    }

    logger.log(`Destroy peer with ID:${this.id}`);

    this.disconnect();
    this._cleanup();

    this._destroyed = true;

    this.emit(PeerEventType.Close);
    }

    /** Disconnects every connection on this peer. */
    private _cleanup(): void {
    for (let peerId of this._connections.keys()) {
      this._cleanupPeer(peerId);
      this._connections.delete(peerId);
    }

    this.socket.removeAllListeners();
    }

    /** Closes all connections to this peer. */
    private _cleanupPeer(peerId: string): void {
    const connections = this._connections.get(peerId);

    if (!connections) return;

    for (let connection of connections) {
      connection.close();
    }
    }

    /**
    * Disconnects the Peer's connection to the PeerServer. Does not close any
    *  active connections.
    * Warning: The peer can no longer create or accept connections after being
    *  disconnected. It also cannot reconnect to the server.
    */
    disconnect(): void {
    if (this.disconnected) {
      return;
    }

    const currentId = this.id;

    logger.log(`Disconnect peer with ID:${currentId}`);

    this._disconnected = true;
    this._open = false;

    this.socket.close();

    this._lastServerId = currentId;
    this._id = null;

    this.emit(PeerEventType.Disconnected, currentId);
    }

    /** Attempts to reconnect with the same ID. */
    reconnect(): void {
    if (this.disconnected && !this.destroyed) {
      logger.log(`Attempting reconnection to server with ID ${this._lastServerId}`);
      this._disconnected = false;
      this._initialize(this._lastServerId!);
    } else if (this.destroyed) {
      throw new Error("This peer cannot reconnect to the server. It has already been destroyed.");
    } else if (!this.disconnected && !this.open) {
      // Do nothing. We're still connecting the first time.
      logger.error("In a hurry? We're still trying to make the initial connection!");
    } else {
      throw new Error(`Peer ${this.id} cannot reconnect because it is not disconnected from the server!`);
    }
    }

    /**
    * Get a list of available peer IDs. If you're running your own server, you'll
    * want to set allow_discovery: true in the PeerServer options. If you're using
    * the cloud server, email team@peerjs.com to get the functionality enabled for
    * your key.
    */
    listAllPeers(cb = (_: any[]) => { }): void {
    this._api.listAllPeers()
      .then(peers => cb(peers))
      .catch(error => this._abort(PeerErrorType.ServerError, error));
    }
    }
