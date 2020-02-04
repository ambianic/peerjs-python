"""Convenience wrapper around RTCDataChannel."""
import asyncio
# from .encodingqueue import EncodingQueue
import json
import logging
from typing import Any

from aiortc import RTCDataChannel

from .baseconnection import BaseConnection
from .enums import (
    ConnectionEventType,
    ConnectionType,
    SerializationType,
    ServerMessageType,
)
from .negotiator import Negotiator
from .servermessage import ServerMessage
from .util import util

log = logging.getLogger(__name__)


class DataConnection(BaseConnection):
    """Wrap a DataChannel between two Peers."""

    ID_PREFIX = "dc_"
    MAX_BUFFERED_AMOUNT = 8 * 1024 * 1024

    @property
    def type(self):
        """Return ConnectionType.Data."""
        return ConnectionType.Data

    @property
    def dataChannel(self) -> RTCDataChannel:
        """Return the RTCDataChannel of this data connection."""
        return self._dc

    def bufferSize(self) -> int:
        """Return current data buffer size."""
        return self._bufferSize

    def __init__(self,
                 peerId: str = None,
                 provider=None,  # provider: Peer
                 **options
                 ):
        """Create a DataConnection instance."""
        super().__init__(peerId, provider, **options)
        self.options = options

        def _apply_options(
            connectionId: str = None,
            label: str = None,
            serialization: str = None,
            reliable: bool = None,
            _payload: Any = None,
            **kwargs
              ):
            self.connectionId: str = \
                connectionId or \
                DataConnection.ID_PREFIX + util.randomToken()
            self.label: str = label or self.connectionId
            self.serialization: SerializationType = \
                serialization or SerializationType.Binary
            self.reliable: bool = reliable
            self._payload = _payload

        log.debug('Applying DataConnection options:\n%r', options)
        _apply_options(**options)
        self.peerId = peerId
        self._negotiator: Negotiator = None
        self.stringify = lambda data: json.dumps(data)
        self.parse = lambda jsn: json.loads(jsn)
        self._buffer: []
        self._bufferSize = 0
        self._buffering = False
        self._chunkedData = {}
        # {
        #     [id: number]: {
        #         data: Blob[],
        #         count: number,
        #         total: number
        #         }
        # }

        self._dc: RTCDataChannel = None
        self._encodingQueue = None  # EncodingQueue()
        # @self._encodingQueue.on('done')
        # def on_eq_done(ab):  # ab : ArrayBuffer
        #     self._bufferedSend(ab)
        #
        # @self._encodingQueue.on('error')
        # def on_eq_error():
        #     log.error(f'DC#${self.connectionId}: '
        #               'Error occured in encoding from blob to arraybuffer, '
        #               'closing Data Connection.')
        #     self.close()
        self._negotiator = Negotiator(self)

    async def start(self):
        """Start data connection negotiation."""
        payload_options = self._payload or {'originator': True}
        log.debug('\n Starting new connection with payload: \n%r '
                  '\n and payload_options: \n%r',
                  self._payload,
                  payload_options)
        await self._negotiator.startConnection(**payload_options)

    async def initialize(self, dc: RTCDataChannel) -> None:
        """Configure datachannel when available.

        Called by the Negotiator when the DataChannel is ready.
        """
        self._dc = dc
        await self._configureDataChannel()

    async def _configureDataChannel(self) -> None:
        if not util.supports.binaryBlob or util.supports.reliable:
            self.dataChannel.binaryType = "arraybuffer"

        log.debug('Configuring DataChannel')

        @self.dataChannel.on('open')
        async def on_datachannel_open():
            log.debug(f'DC#${self.connectionId} dc connection success')
            log.debug('DataChannel open. Transport capabilities: \n%r',
                      self.dataChannel.transport.getCapabilities())
            self._open = True
            self.emit(ConnectionEventType.Open)

        if self.dataChannel.readyState == 'open':
            # dataChannel already moved to open state
            # and we may miss the 'open' event
            # so lets not rely on that
            await on_datachannel_open()

        @self.dataChannel.on('message')
        async def on_datachannel_message(msg):
            log.debug(f'DC#${self.connectionId} received message')
            await self._handleDataMessage(msg)

        @self.dataChannel.on('close')
        async def on_datachannel_close():
            log.debug(f'DC#${self.connectionId} dc closed for: {self.peer}')
            await self.close()

    async def _handleDataMessage(self, data) -> None:
        """Handle a DataChannel message."""
        log.debug('\n Received data (type %s) from remote peer: \n%r',
                  type(data),
                  data)
        log.debug('Serialization type: %s', self.serialization)
        isBinarySerialization = \
            self.serialization == SerializationType.Binary or \
            self.serialization == SerializationType.BinaryUTF8
        log.debug('isBinarySerialization: %r',
                  isBinarySerialization)
        deserializedData = data
        # Peerjs JavaScript version uses a messagepack library
        #   which is not ported to Python yet
        if isBinarySerialization:
            #     if datatype == Blob:
            #         # Datatype should never be blob
            #         ab = await util.blobToArrayBuffer(data)
            #         unpackedData = util.unpack(ab)
            #         self.emit(ConnectionEventType.Data, unpackedData)
            #         return
            if isinstance(data, bytes):
                log.warning('Unpacking data...')
                deserializedData = util.unpack(data)
            #     elif datatype == String:
            #         # String fallback for binary data for browsers
            #         # that don't support binary yet
            #         ab = util.binaryStringToArrayBuffer(data)
            #         deserializedData = util.unpack(ab)
        if self.serialization == SerializationType.Raw:
            # no special manipulation of deserialized data
            pass
        elif self.serialization == SerializationType.JSON:
            deserializedData = self.parse(data)

        # log.debug('\n Deserialized data (type %s): \n%r',
        #           type(deserializedData),
        #           deserializedData)
        #
        # if isinstance(deserializedData, str):
        #     log.warning('\n Deserialized string %s',
        #                 deserializedData)

        # Check if we've chunked--if so, piece things back together.
        # We're guaranteed that this isn't 0.
        # if deserializedData.get('__peerData', None):
        #     await self._handleChunk(deserializedData)
        #     return

        self.emit(ConnectionEventType.Data, deserializedData)

    async def _handleChunk(self, data) -> None:
        id = data.__peerData
        chunkInfo = self._chunkedData[id] or {
          'data': [],
          'count': 0,
          'total': data.total
        }
        chunkInfo.data[data.n] = data.data
        chunkInfo.count += 1
        self._chunkedData[id] = chunkInfo
        if chunkInfo.total == chunkInfo.count:
            # Clean up before making
            # the recursive call to `_handleDataMessage`.
            del self._chunkedData[id]
            # We've received all the chunks--time
            # to construct the complete data.
            # Blog is a browser JavaScript type.
            # Not applicable in the Python port.
            # data = Blob(chunkInfo.data)
            await self._handleDataMessage(data)

    #
    # Exposed functionality for users.
    #

    async def close(self) -> None:
        """Close this connection."""
        self._buffer = []
        self._bufferSize = 0
        self._chunkedData = {}
        if self._negotiator:
            await self._negotiator.cleanup()
            self._negotiator = None
        if self.provider:  # provider: Peer
            self.provider._removeConnection(self)
        self.provider = None
        if self.dataChannel:
            self.dataChannel.remove_all_listeners()
            self._dc = None
        if self._encodingQueue:
            self._encodingQueue.destroy()
            self._encodingQueue.remove_all_listeners()
            self._encodingQueue = None
        if not self.open:
            return
        self._open = False
        self.emit(ConnectionEventType.Close)

    async def send(self, data, chunked: bool = False) -> None:
        """Send data to the peer on the other side of this connection."""
        log.debug('DataConnection entered send(data): \n%r', data)
        if not self.open:
            log.warning('DataConnection not open')
            self.emit(
                ConnectionEventType.Error,
                RuntimeError(
                    'Connection is not open. '
                    'You should listen for the `open` '
                    'event before sending messages.'
                )
            )
            return

        log.debug('Serialization: %r', self.serialization)

        if self.serialization == SerializationType.JSON:
            log.warning('DataConnection sending JSON data: \n%r', data)
            await self._bufferedSend(self.stringify(data))
        # Blob is a JavaScript browser type. Not supported in Python.
        # elif \
        #     self.serialization == SerializationType.Binary or \
        #         self.serialization == SerializationType.BinaryUTF8:
        #     blob = util.pack(data)
        #     if not chunked and blob.size > util.chunkedMTU:
        #         self._sendChunks(blob)
        #         return
        #
        #     if not util.supports.binaryBlob:
        #         # We only do this if we really need to
        #         # (e.g. blobs are not supported),
        #         # because this conversion is costly.
        #         self._encodingQueue.enque(blob)
        #     else:
        #         self._bufferedSend(blob)
        else:
            # log.debug('DataConnection sending data: \n%r', data)
            await self._bufferedSend(data)

    async def _bufferedSend(self, msg: any) -> None:
        if self._buffering or not await self._trySend(msg):
            self._buffer.push(msg)
            self._bufferSize = self._buffer.length

    async def _trySend(self, msg) -> bool:
        """Return true if the send succeeds."""
        log.debug('DataChannel entered _trySend(msg): \n%r', msg)
        if not self.open:
            return False
        if self.dataChannel.bufferedAmount > \
           DataConnection.MAX_BUFFERED_AMOUNT:
            self._buffering = True

            async def delayBuf():
                # wait for 50ms before trying buffer
                await asyncio.sleep(0.05)
                self._buffering = False
                self._tryBuffer()
            asyncio.create_task(delayBuf())
            return False
        try:
            log.debug('DataChannel sending message: \n%r', msg)
            self.dataChannel.send(msg)
        except Exception as e:
            log.exception(f'DC#:${self.connectionId} Error when sending: {e}')
            self._buffering = True
            await self.close()
            return False
        return True

    def _tryBuffer(self) -> None:
        """Try to send the first message in the buffer."""
        if not self.open:
            return
        if self._buffer.length == 0:
            return

        msg = self._buffer[0]

        if self._trySend(msg):
            self._buffer.shift()
            self._bufferSize = self._buffer.length
            self._tryBuffer()

    # def _sendChunks(self, blob: Blob) -> None:
    #     blobs = util.chunk(blob)
    #     log.debug(f'DC#${this.connectionId} '
    #               f'Try to send ${blobs.length} chunks...')
    #     for blob in blobs:
    #         self.send(blob, True)

    async def handleMessage(self, message: ServerMessage) -> None:
        """Handle signaling server message."""
        payload = message.payload
        if message.type == ServerMessageType.Answer:
            await self._negotiator.handleSDP(message.type, payload.sdp)
        elif message.type == ServerMessageType.Candidate:
            await self._negotiator.handleCandidate(payload['candidate'])
        else:
            log.warning(
              f"Unrecognized message type: {message.type}"
              "from peer: {this.peer}"
            )
