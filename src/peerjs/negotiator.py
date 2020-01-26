"""Constructs for managing negotiations between Peers."""
import logging

# from .dataconnection import DataConnection
from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription
from aiortc.sdp import candidate_from_sdp, candidate_to_sdp
from pyee import AsyncIOEventEmitter
# import { MediaConnection } from "./mediaconnection";
from .enums import ConnectionEventType, ConnectionType, PeerErrorType, ServerMessageType
from .util import util
from .baseconnection import BaseConnection

log = logging.getLogger(__name__)


def object_to_dict(obj):
    """Convert RTC object to dict."""
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
    return message


class Negotiator:
    """Manages all negotiations between Peers."""

    def __init__(self, connection: BaseConnection = None):
        """Create negotiator."""
        self.connection = connection

    async def startConnection(
            self,
            originator=None,
            sdp: dict = None,
            _stream=None,
            reliable=None,
            type=None,
            **options) -> RTCPeerConnection:
        """Return a PeerConnection object setup correctly for data or media."""
        peerConnection = self._startPeerConnection()
        # Set the connection wrapper's RTCPeerConnection.
        self.connection.peerConnection = peerConnection
        if self.connection.type == ConnectionType.Media and _stream:
            self._addTracksToConnection(_stream, peerConnection)
        # What do we need to do now?
        if originator:
            # originate connection offer
            if self.connection.type == ConnectionType.Data:
                dataConnection: DataConnection = self.connection  # NOQA
                # Pass RTCDataChannelInit dictionary
                # https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/createDataChannel#RTCDataChannelInit_dictionary
                log.info('creating datachannel with label=%s and ordered=%s',
                         dataConnection.label, reliable)
                dataChannel = peerConnection.createDataChannel(
                    dataConnection.label, ordered=reliable)
                await dataConnection.initialize(dataChannel)
            await self._makeOffer()
        else:
            # receive connection offer originated by remote peer
            await self.handleSDP(type=ServerMessageType.Offer, sdp=sdp)

    def _startPeerConnection(self) -> RTCPeerConnection:
        """Start a Peer Connection."""
        config = self.connection.provider.options.config
        log.debug("Creating RTCPeerConnection with config:\n%r", config)
        peerConnection = RTCPeerConnection(config)
        self._setupListeners(peerConnection)
        return peerConnection

    def _setupListeners(self, peerConnection: RTCPeerConnection = None):
        """Set up various WebRTC listeners."""
        peerId = self.connection.peer
        connectionId = self.connection.connectionId
        # connectionType = self.connection.type
        provider = self.connection.provider

        # ICE CANDIDATES.
        log.debug("Listening for ICE candidates.")

        @peerConnection.on('icegatheringstatechange')
        def peerconn_icegatheringstatechange():
            if peerConnection.iceGatheringState == 'complete':
                log.debug('Local ICE candidates gathered.')

        @peerConnection.on('iceconnectionstatechange')
        def peerconn_oniceconnectionstatechange():
            state_change = AsyncIOEventEmitter()
            @state_change.once("failed")
            async def on_failed(error=None):
                log.warning(
                    "\n IceConnectionState failed with error %s "
                    "\n Closing connections to peer id %s",
                    error,
                    peerId
                    )
                self.connection.emit(
                    ConnectionEventType.Error,
                    ConnectionError(
                        f"Negotiation of connection to {peerId} failed.")
                    )
                await self.connection.close()

            @state_change.once("closed")
            def on_closed():
                log.info(
                    "iceConnectionState is closed, "
                    f"closing connections to {peerId}"
                    )
                self.connection.emit(
                    ConnectionEventType.Error,
                    ConnectionError(f"Connection to {peerId} closed.")
                    )
                self.connection.close()

            @state_change.once("disconnected")
            def on_disconnected():
                log.info(
                    "iceConnectionState is disconnected, "
                    f"closing connections to {peerId}"
                    )
                self.connection.emit(
                    ConnectionEventType.Error,
                    ConnectionError(f"Connection to {peerId} disconnected.")
                    )
                self.connection.close()

            @state_change.once("completed")
            def on_completed():
                log.debug(
                    'iceConnectionState completed for peer id %s',
                    peerId
                    )
                # this function needs to be implemented as in PeerJS
                # https://github.com/peers/peerjs/blob/5e36ba17be02a9af7c171399f7737d8ccb38fbbe/lib/negotiator.ts#L119
                # when the "icecandidate"
                # event handling issue above is resolved
                # peerConnection.remove_listener("icecandidate",
                #       peerconn_onicecandidate)
                pass

            log.debug(
                'iceConnectionState event: %s',
                peerConnection.iceConnectionState
                )
            # forward connection stage change event to local handlers
            state_change.emit(peerConnection.iceConnectionState)
            # notify higher level connection listeners
            self.connection.emit(ConnectionEventType.IceStateChanged,
                                 peerConnection.iceConnectionState)

        # DATACONNECTION.
        log.debug("Listening for data channel events.")
        # Fired between offer and answer, so options should already be saved
        # in the options hash.
        @peerConnection.on("datachannel")
        async def peerconn_ondatachanel(dataChannel):
            log.debug("Received data channel %r", dataChannel)
            connection = provider.getConnection(peerId, connectionId)
            await connection.initialize(dataChannel)

        # MEDIACONNECTION.
        log.debug("Listening for remote stream.")
        @peerConnection.on("track")
        def peerconn_ontrack(evt):
            log.info("Received remote stream.")
            stream = evt.streams[0]
            connection = provider.getConnection(peerId, connectionId)
            if connection.type == ConnectionType.Media:
                mediaConnection = connection
                self._addStreamToMediaConnection(stream, mediaConnection)

    async def cleanup(self) -> None:
        """Clean up resources after connection closes."""
        log.debug("Closing and cleaning up PeerConnection to %s",
                  self.connection.peer)
        peerConnection = self.connection.peerConnection
        if not peerConnection:
            return
        self.connection.peerConnection = None
        # unsubscribe from all PeerConnection's events
        peerConnection.remove_all_listeners()
        peerConnectionNotClosed = peerConnection.signalingState != "closed"
        dataChannelNotClosed = False
        if self.connection.type == ConnectionType.Data:
            dataConnection: DataConnection = self.connection  # NOQA
            dataChannel = dataConnection.dataChannel
            if dataChannel:
                dataChannelNotClosed = dataChannel.readyState and \
                    dataChannel.readyState != "closed"
        if peerConnectionNotClosed or dataChannelNotClosed:
            try:
                await peerConnection.close()
            except Exception as err:
                log.exception('Error while closing connection %r', err)

    async def _makeOffer(self):
        peerConnection = self.connection.peerConnection
        provider = self.connection.provider
        try:
            offer = await peerConnection.createOffer(
                self.connection.options.constraints)
            log.info("Created offer.")

            if self.connection.options.sdpTransform and \
               callable(self.connection.options.sdpTransform):
                tSDP = self.connection.options.sdpTransform(offer.sdp)
                if tSDP:
                    offer.sdp = tSDP
            try:
                await peerConnection.setLocalDescription(offer)
                log.info(f"Set localDescription:{offer} "
                         f"for: {self.connection.peer}")
                payload = {
                    'sdp': offer,
                    'type': self.connection.type,
                    'connectionId': self.connection.connectionId,
                    'metadata': self.connection.metadata,
                    'browser': util.browser
                    }
                if self.connection.type == ConnectionType.Data:
                    dataConnection = self.connection
                    payload.update({
                        'label': dataConnection.label,
                        'reliable': dataConnection.reliable,
                        'serialization': dataConnection.serialization
                        })
                await provider.socket.send({
                  'type': ServerMessageType.Offer.value,
                  'payload': payload,
                  'dst': self.connection.peer
                })
            except Exception as err:
                # TODO: investigate why _makeOffer
                # is being called from the answer
                if err != \
                  "OperationError: Failed to set local offer sdp: " \
                  "Called in wrong state: kHaveRemoteOffer":
                    provider.emitError(PeerErrorType.WebRTC, err)
                    log.debug("Failed to setLocalDescription, ", err)
        except Exception as err_1:
            provider.emitError(PeerErrorType.WebRTC, err_1)
            log.debug("Failed to createOffer, ", err_1)

    async def _makeAnswer(self) -> None:
        peerConnection = self.connection.peerConnection
        provider = self.connection.provider
        try:
            answer = await peerConnection.createAnswer()
            sdpTransformFunction = \
                self.connection.options.get('sdpTransform', None)
            if sdpTransformFunction and \
               callable(sdpTransformFunction):
                answer.sdp = sdpTransformFunction(answer.sdp) \
                    or answer.sdp
            log.debug('\n Created answer header: \n %r', answer)
            log.debug('\n Connection options: %r', self.connection.options)
            try:
                log.info('Gathering ICE candidates to complete answer...')
                await peerConnection.setLocalDescription(answer)
                answer = peerConnection.localDescription
                json_answer = object_to_dict(answer)
                log.debug('\n Sending SDP ANSWER to peer id %s: \n %r ',
                          self.connection.peer,
                          json_answer)
                await provider.socket.send({
                    'type': ServerMessageType.Answer.value,
                    'payload': {
                        'sdp': json_answer,
                        'type': self.connection.type.value,
                        'connectionId': self.connection.connectionId,
                        'browser': util.browser
                        },
                    'dst': self.connection.peer
                    })
            except Exception as err:
                provider.emitError(PeerErrorType.WebRTC, err)
                log.exception("Failed to setLocalDescription, ", err)
        except Exception as err_1:
            provider.emitError(PeerErrorType.WebRTC, err_1)
            log.exception("Failed to create answer, ", err_1)

    async def handleSDP(self,
                        type: ServerMessageType = None,
                        sdp: dict = None) -> None:
        """Handle an SDP."""
        rsd = RTCSessionDescription(**sdp)
        peerConnection = self.connection.peerConnection
        provider = self.connection.provider
        log.debug("\n Setting remote session description \n %r", rsd)
        try:
            await peerConnection.setRemoteDescription(rsd)
            log.debug('\n Set remoteDescription type: %s'
                      '\n for peer: %r',
                      type, self.connection.peer)
            if type == ServerMessageType.Offer:
                await self._makeAnswer()
        except Exception as err:
            provider.emitError(PeerErrorType.WebRTC, err)
            log.exception("Failed to setRemoteDescription", err)

    async def handleCandidate(self, ice=None):
        """Handle new peer candidate."""
        log.debug(f'handleCandidate:', ice)
        candidate = ice['candidate']
        sdpMLineIndex = ice['sdpMLineIndex']
        sdpMid = ice['sdpMid']
        peerConnection = self.connection.peerConnection
        provider = self.connection.provider
        try:
            log.debug('Adding ICE candidate for peer id %s',
                      self.connection.peer)
            rtc_ice_candidate = candidate_from_sdp(candidate)
            rtc_ice_candidate.sdpMid = sdpMid
            rtc_ice_candidate.sdpMLineIndex = sdpMLineIndex
            log.debug('RTCIceCandidate: %r', rtc_ice_candidate)
            log.debug('peerConnection: %r', peerConnection)
            peerConnection.addIceCandidate(rtc_ice_candidate)
            log.debug('Added ICE candidate for peer %s',
                      self.connection.peer)
        except Exception as err:
            provider.emitError(PeerErrorType.WebRTC, err)
            log.exception("Failed to handleCandidate, ", err)

    def _addTracksToConnection(
         stream,  #: MediaStream
         peerConnection: RTCPeerConnection
         ) -> None:
        log.debug(f'add tracks from stream ${stream.id} to peer connection')
        if not peerConnection.addTrack:
            return log.error(
                f"Your browser does't support RTCPeerConnection#addTrack. "
                "Ignored."
                )
        tracks = stream.getTracks()
        for track in tracks:
            peerConnection.addTrack(track, stream)

    def _addStreamToMediaConnection(
         stream,  # : MediaStream,
         mediaConnection  # : MediaConnection
         ) -> None:
        log.debug(
            f'add stream {stream.id} to media connection '
            f'{mediaConnection.connectionId}'
            )
        mediaConnection.addStream(stream)
