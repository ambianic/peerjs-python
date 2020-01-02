"""Convenience wrapper around RTCDataChannel."""
from util import util
import logging
from negotiator import Negotiator
from enums import \
  ConnectionType, \
  ConnectionEventType, \
  SerializationType, \
  ServerMessageType
from .baseconnection import BaseConnection
from .servermessage import ServerMessage
from .encodingqueue import EncodingQueue
import json
from aiortc import RTCDataChannel

log = logging.getLogger(__name__)


class DataConnection(BaseConnection):
    """Wraps a DataChannel between two Peers."""
    ID_PREFIX = "dc_"
    MAX_BUFFERED_AMOUNT = 8 * 1024 * 1024

    @property
    def type():
        return ConnectionType.Data

    @property
    def dataChannel() -> RTCDataChannel:
        return self._dc

    def bufferSize() -> int:
        return self._bufferSize

    def __init__(self, peerId: str, provider: Peer, **options):
        super(peerId, provider, options)
        _negotiator: Negotiator
        label: str
        serialization: SerializationType
        reliable: boolean
        stringify: lambda data: json.dumps(data)
        parse: lambda jsn: json.loads(jsn)
        _buffer: []
        _bufferSize = 0
        _buffering = False
        _chunkedData = {}
        # {
        #     [id: number]: {
        #         data: Blob[],
        #         count: number,
        #         total: number
        #         }
        # }

        _dc: RTCDataChannel
        _encodingQueue = EncodingQueue()
        if self.options.connectionId:
            self.connectionId = self.options.connectionId
        else:
            self.connectionId = DataConnection.ID_PREFIX + util.randomToken()
        if self.options.label:
            self.label = this.options.label
        else:
            self.label = self.connectionId
        self.serialization = self.options.serialization if \
            self.options.serialization else SerializationType.Binary
        self.reliable = self.options.reliable
        @self._encodingQueue.on('done')
        def on_eq_done(ab: ArrayBuffer):
            self._bufferedSend(ab)

        @self._encodingQueue.on('error')
        def on_eq_error():
            log.error(f'DC#${this.connectionId}: '
                      'Error occured in encoding from blob to arraybuffer, '
                      'closing Data Connection.')
            self.close()
        self._negotiator = Negotiator(self)
        payload_option = self.options._payload or {'originator': true}
        self._negotiator.startConnection()

    def initialize(self, dc: RTCDataChannel) -> None:
        """Called by the Negotiator when the DataChannel is ready."""
        self._dc = dc
        self._configureDataChannel()

    def _configureDataChannel(self) -> None:
        if not util.supports.binaryBlob or util.supports.reliable:
            this.dataChannel.binaryType = "arraybuffer"

        @self.dataChannel.on('open')
        def on_datachannel_open():
            log.debug(f'DC#${this.connectionId} dc connection success')
            self._open = True
            self.emit(ConnectionEventType.Open)

        @self.dataChannel.on('message')
        def on_datachannel_message(e):
            log.debug(f'DC#${self.connectionId} dc onmessage: {e.data}')
            self._handleDataMessage(e)

        @self.dataChannel.on('close')
        def on_datachannel_close(e):
            log.debug(f'DC#${self.connectionId} dc closed for: {self.peer}')
            self.close()

    def _handleDataMessage(self, data) -> None:
        """Handles a DataChannel message."""
        datatype = data.constructor

        isBinarySerialization = \
            self.serialization == SerializationType.Binary or \
            self.serialization == SerializationType.BinaryUTF8

        deserializedData = data

        if isBinarySerialization:
            if datatype == Blob:
                # Datatype should never be blob
                ab = await util.blobToArrayBuffer(data)
                unpackedData = util.unpack(ab)
                self.emit(ConnectionEventType.Data, unpackedData)
                return
            if datatype == ArrayBuffer:
                deserializedData = util.unpack(data)
            elif datatype == String:
                # String fallback for binary data for browsers
                # that don't support binary yet
                ab = util.binaryStringToArrayBuffer(data)
                deserializedData = util.unpack(ab)
        elif self.serialization == SerializationType.JSON:
            deserializedData = self.parse(data)

        # Check if we've chunked--if so, piece things back together.
        # We're guaranteed that this isn't 0.
        if deserializedData.__peerData:
            self._handleChunk(deserializedData)
            return

        self.emit(ConnectionEventType.Data, deserializedData)

    def _handleChunk(self, data) -> None:
        id = data.__peerData
        chunkInfo = self._chunkedData[id] or {
          'data': [],
          'count': 0,
          'total': data.total
        }
        chunkInfo.data[data.n] = data.data
        chunkInfo.count += 1
        this._chunkedData[id] = chunkInfo
        if chunkInfo.total == chunkInfo.count:
            # Clean up before making
            # the recursive call to `_handleDataMessage`.
            del self._chunkedData[id]
            # We've received all the chunks--time
            # to construct the complete data.
            data = Blob(chunkInfo.data)
            this._handleDataMessage(data)

    #
    # Exposed functionality for users.
    #

    def close(self) -> None:
        """Close this connection."""
        self._buffer = []
        self._bufferSize = 0
        self._chunkedData = {}
        if self._negotiator:
            self._negotiator.cleanup()
            self._negotiator = None
        if self.provider:
            self.provider._removeConnection(self)
        self.provider = None
        if self.dataChannel:
            self.dataChannel.onopen = None
            self.dataChannel.onmessage = None
            self.dataChannel.onclose = None
            self._dc = null
        if self._encodingQueue:
            self._encodingQueue.destroy()
            self._encodingQueue.removeAllListeners()
            self._encodingQueue = None
        if not self.open:
            return
        self._open = False
        self.emit(ConnectionEventType.Close)

    def send(self, data, chunked: bool) -> None:
        """Send data to the peer on the other side of this connection."""
        if not self.open:
            self.emit(
                ConnectionEventType.Error,
                RuntimrError(
                    'Connection is not open. '
                    'You should listen for the `open` '
                    'event before sending messages.'
                )
            )
            return

        if self.serialization == SerializationType.JSON:
            self._bufferedSend(this.stringify(data))
        elif \
            self.serialization == SerializationType.Binary or \
                self.serialization == SerializationType.BinaryUTF8:
            blob = util.pack(data)
            if not chunked and blob.size > util.chunkedMTU:
                self._sendChunks(blob)
                return

            if not util.supports.binaryBlob:
                # We only do this if we really need to
                # (e.g. blobs are not supported),
                # because this conversion is costly.
                self._encodingQueue.enque(blob)
            else:
                self._bufferedSend(blob)
        else:
            self._bufferedSend(data)

    def _bufferedSend(self, msg: any) -> None:
        if self._buffering or not self._trySend(msg):
            self._buffer.push(msg)
            self._bufferSize = this._buffer.length

    async def _trySend(self, msg) -> bool:
        """Returns true if the send succeeds."""
        if not this.open:
            return false
        if self.dataChannel.bufferedAmount > \
           DataConnection.MAX_BUFFERED_AMOUNT:
            self._buffering = true

            def delayBuf():
                # wait for 50ms before trying buffer
                await asyncio.sleep(0.05)
                self._buffering = False
                self._tryBuffer()
            asyncio.create_task(delayBuf)
            return False
        try:
            self.dataChannel.send(msg)
        except Exception as e:
            log.error(f'DC#:${this.connectionId} Error when sending: {e}')
            self._buffering = True
            self.close()
            return False
        return True

    def _tryBuffer(self) -> None:
        """Try to send the first message in the buffer."""
        if not this.open:
            return
        if self._buffer.length == 0:
            return

        msg = this._buffer[0]

        if self._trySend(msg):
            self._buffer.shift()
            self._bufferSize = self._buffer.length
            self._tryBuffer()

    def _sendChunks(self, blob: Blob) -> None:
        blobs = util.chunk(blob)
        log.debug(f'DC#${this.connectionId} '
                  f'Try to send ${blobs.length} chunks...')
        for blob in blobs:
            self.send(blob, True)

    def handleMessage(self, message: ServerMessage) -> None:
        payload = message.payload
        if message.type == ServerMessageType.Answer:
            self._negotiator.handleSDP(message.type, payload.sdp)
        elif message.type == ServerMessageType.Candidate:
            self._negotiator.handleCandidate(payload.candidate)
        else:
            log.warning(
              f"Unrecognized message type: {message.type}"
              "from peer: {this.peer}"
            )
