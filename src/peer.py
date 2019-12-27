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

class PeerConnectOption:
    def __init__(self):
        self.label: str = None
        self.metadata = None
        self.serialization: str = None
        self.reliable: bool = None

class PeerOptions:
    def __init__(self):
        self.debug: int = 1  # 1: Errors, 2: Warnings, 3: All logs
        self.host: str = None
        self.port: int = None
        self.path: str = None
        self.key: str = None
        self.token: str = None
        self.config = None
        self.secure: bool = None
        self.pingInterval: int = None


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
    """A peer that can initiate connections with other peers."""

  get id() {
    return this._id;
  }

  get options() {
    return this._options;
  }

  get open() {
    return this._open;
  }

  get socket() {
    return this._socket;
  }

  /**
   * @deprecated
   * Return type will change from Object to Map<string,[]>
   */
  get connections(): Object {
    const plainConnections = Object.create(null);

    for (let [k, v] of this._connections) {
      plainConnections[k] = v;
    }

    return plainConnections;
  }

  get destroyed() {
    return this._destroyed;
  }
  get disconnected() {
    return this._disconnected;
  }

  def __init__(self, id: str = None, options: PeerOptions = None) {
    self.super();

    self._DEFAULT_KEY = "peerjs";

    self._options: PeerOptions;
    self._api: API;
    self._socket: Socket;

    self._id: str = id;
    self._lastServerId: str = None

    # States.
    self._destroyed = false; // Connections have been killed
    self._disconnected = false; // Connection to PeerServer killed but P2P connections still active
    self._open = false; // Sockets and such are not yet open.
    self._connections: dict = {}  # All connections for this peer.
    self._lostMessages: dict = {}  # src => [list of server messages]

    userId: str = None

    # Deal with overloading
    if id:
      userId = id

    # Configure options
    options = {
      debug: 0,  # 1: Errors, 2: Warnings, 3: All logs
      host: util.CLOUD_HOST,
      port: util.CLOUD_PORT,
      path: "/",
      key: Peer.DEFAULT_KEY,
      token: util.randomToken(),
      config: util.defaultConfig,
      ...options
    };
    this._options = options;

    // Detect relative URL host.
    if (this._options.host === "/") {
      this._options.host = window.location.hostname;
    }

    // Set path correctly.
    if (this._options.path) {
      if (this._options.path[0] !== "/") {
        this._options.path = "/" + this._options.path;
      }
      if (this._options.path[this._options.path.length - 1] !== "/") {
        this._options.path += "/";
      }
    }

    // Set whether we use SSL to same as current host
    if (this._options.secure === undefined && this._options.host !== util.CLOUD_HOST) {
      this._options.secure = util.isSecure();
    } else if (this._options.host == util.CLOUD_HOST) {
      this._options.secure = true;
    }
    // Set a custom log function if present
    if (this._options.logFunction) {
      logger.setLogFunction(this._options.logFunction);
    }

    logger.logLevel = this._options.debug || 0;

    this._api = new API(options);
    this._socket = this._createServerConnection();

    // Sanity checks
    // Ensure WebRTC supported
    if (!util.supports.audioVideo && !util.supports.data) {
      this._delayedAbort(
        PeerErrorType.BrowserIncompatible,
        "The current browser does not support WebRTC"
      );
      return;
    }

    // Ensure alphanumeric id
    if (!!userId && !util.validateId(userId)) {
      this._delayedAbort(PeerErrorType.InvalidID, `ID "${userId}" is invalid`);
      return;
    }

    if (userId) {
      this._initialize(userId);
    } else {
      this._api.retrieveId()
        .then(id => this._initialize(id))
        .catch(error => this._abort(PeerErrorType.ServerError, error));
    }
  }

  private _createServerConnection(): Socket {
    const socket = new Socket(
      this._options.secure,
      this._options.host!,
      this._options.port!,
      this._options.path!,
      this._options.key!,
      this._options.pingInterval
    );

    socket.on(SocketEventType.Message, (data: ServerMessage) => {
      this._handleMessage(data);
    });

    socket.on(SocketEventType.Error, (error: string) => {
      this._abort(PeerErrorType.SocketError, error);
    });

    socket.on(SocketEventType.Disconnected, () => {
      if (this.disconnected) {
        return;
      }

      this.emitError(PeerErrorType.Network, "Lost connection to server.");
      this.disconnect();
    });

    socket.on(SocketEventType.Close, () => {
      if (this.disconnected) {
        return;
      }

      this._abort(PeerErrorType.SocketClosed, "Underlying socket is already closed.");
    });

    return socket;
  }

  /** Initialize a connection with the server. */
  private _initialize(id: string): void {
    this._id = id;
    this.socket.start(id, this._options.token!);
  }

  /** Handles messages from the server. */
  private _handleMessage(message: ServerMessage): void {
    const type = message.type;
    const payload = message.payload;
    const peerId = message.src;

    switch (type) {
      case ServerMessageType.Open: // The connection to the server is open.
        this._lastServerId = this.id;
        this._open = true;
        this.emit(PeerEventType.Open, this.id);
        break;
      case ServerMessageType.Error: // Server error.
        this._abort(PeerErrorType.ServerError, payload.msg);
        break;
      case ServerMessageType.IdTaken: // The selected ID is taken.
        this._abort(PeerErrorType.UnavailableID, `ID "${this.id}" is taken`);
        break;
      case ServerMessageType.InvalidKey: // The given API key cannot be found.
        this._abort(PeerErrorType.InvalidKey, `API KEY "${this._options.key}" is invalid`);
        break;
      case ServerMessageType.Leave: // Another peer has closed its connection to this peer.
        logger.log(`Received leave message from ${peerId}`);
        this._cleanupPeer(peerId);
        this._connections.delete(peerId);
        break;
      case ServerMessageType.Expire: // The offer sent to a peer has expired without response.
        this.emitError(PeerErrorType.PeerUnavailable, `Could not connect to peer ${peerId}`);
        break;
      case ServerMessageType.Offer: {
        // we should consider switching this to CALL/CONNECT, but this is the least breaking option.
        const connectionId = payload.connectionId;
        let connection = this.getConnection(peerId, connectionId);

        if (connection) {
          connection.close();
          logger.warn(`Offer received for existing Connection ID:${connectionId}`);
        }

        // Create a new connection.
        if (payload.type === ConnectionType.Media) {
          connection = new MediaConnection(peerId, this, {
            connectionId: connectionId,
            _payload: payload,
            metadata: payload.metadata
          });
          this._addConnection(peerId, connection);
          this.emit(PeerEventType.Call, connection);
        } else if (payload.type === ConnectionType.Data) {
          connection = new DataConnection(peerId, this, {
            connectionId: connectionId,
            _payload: payload,
            metadata: payload.metadata,
            label: payload.label,
            serialization: payload.serialization,
            reliable: payload.reliable
          });
          this._addConnection(peerId, connection);
          this.emit(PeerEventType.Connection, connection);
        } else {
          logger.warn(`Received malformed connection type:${payload.type}`);
          return;
        }

        // Find messages.
        const messages = this._getMessages(connectionId);
        for (let message of messages) {
          connection.handleMessage(message);
        }

        break;
      }
      default: {
        if (!payload) {
          logger.warn(`You received a malformed message from ${peerId} of type ${type}`);
          return;
        }

        const connectionId = payload.connectionId;
        const connection = this.getConnection(peerId, connectionId);

        if (connection && connection.peerConnection) {
          // Pass it on.
          connection.handleMessage(message);
        } else if (connectionId) {
          // Store for possible later use
          this._storeMessage(connectionId, message);
        } else {
          logger.warn("You received an unrecognized message:", message);
        }
        break;
      }
    }
  }

  /** Stores messages without a set up connection, to be claimed later. */
  private _storeMessage(connectionId: string, message: ServerMessage): void {
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
