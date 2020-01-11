"""Constructs for managing negotiations between Peers."""
import logging

# from .dataconnection import DataConnection
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.sdp import candidate_from_sdp
from pyee import BaseEventEmitter

from .baseconnection import BaseConnection
# import { MediaConnection } from "./mediaconnection";
from .enums import ConnectionEventType, ConnectionType, PeerErrorType, ServerMessageType
from .util import util

log = logging.getLogger(__name__)


class Negotiator:
    """Manages all negotiations between Peers."""

    def __init__(self, connection: BaseConnection = None):
        """Create negotiator."""
        self.connection = connection

    async def startConnection(
            self,
            originator=None,
            sdp: str = None,
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
                dataConnection.initialize(dataChannel)
            await self._makeOffer()
        else:
            # receive connection offer originated by remote peer
            await self.handleSDP(type=type, sdp=sdp)

    def _startPeerConnection(self) -> RTCPeerConnection:
        """Start a Peer Connection."""
        log.debug("Creating RTCPeerConnection.")
        peerConnection = RTCPeerConnection(
            self.connection.provider.options.config)
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
        # Its not clear yet how aiortc supports trickle ice.
        # Open issue: https://github.com/aiortc/aiortc/issues/246
        # def peerconn_onicecandidate
        # peerConnection.onicecandidate = (evt) => {
        #     if (!evt.candidate || !evt.candidate.candidate) return;
        #
        #     logger.log(`Received ICE candidates for ${peerId}:`,
        #               evt.candidate)
        #
        #       provider.socket.send({
        #         type: ServerMessageType.Candidate,
        #         payload: {
        #           candidate: evt.candidate,
        #           type: connectionType,
        #           connectionId: connectionId
        #         },
        #         dst: peerId
        #       });
        #     };

        @peerConnection.on('iceconnectionstatechange')
        def peerconn_oniceconnectionstatechange():
            state_change = BaseEventEmitter()
            @state_change.once("failed")
            def on_failed():
                log.warning(
                    f"iceConnectionState is failed, "
                    "closing connections to {peerId}"
                    )
                self.connection.emit(
                    ConnectionEventType.Error,
                    ConnectionError(
                        f"Negotiation of connection to {peerId} failed.")
                    )
                self.connection.close()

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
                log.info(
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
        def peerconn_ondatachanel(evt):
            log.info("Received data channel.")
            dataChannel = evt.channel
            connection = provider.getConnection(peerId, connectionId)
            connection.initialize(dataChannel)

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
        log.info("Closing and cleaning up PeerConnection to %s",
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
            await peerConnection.close()

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
                provider.socket.send({
                  'type': ServerMessageType.Offer,
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
            log.info("Created answer. Connection options: %r",
                     self.connection.options)
            if self.connection.options.sdpTransform and \
               callable(self.connection.options.sdpTransform):
                answer.sdp = self.connection.options.sdpTransform(answer.sdp) \
                    or answer.sdp
            try:
                await peerConnection.setLocalDescription(answer)
                log.info(f"Set localDescription: {answer}"
                         f"for:{self.connection.peer}")
                provider.socket.send({
                    'type': ServerMessageType.Answer,
                    'payload': {
                        'sdp': answer,
                        'type': self.connection.type,
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

    async def handleSDP(self, type: str = None, sdp: str = None) -> None:
        """Handle an SDP."""
        rsd = RTCSessionDescription(type=type, sdp=sdp)
        peerConnection = self.connection.peerConnection
        provider = self.connection.provider
        log.info("Setting remote session description %r", rsd)
        try:
            await peerConnection.setRemoteDescription(rsd)
            log.info('Set remoteDescription type: %s'
                     'for peer: %r',
                     type, self.connection.peer)
            if type == "offer":
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
            log.info('Adding ICE candidate for peer id %s',
                     self.connection.peer)
            rtc_ice_candidate = candidate_from_sdp(candidate)
            rtc_ice_candidate.sdpMid = sdpMid
            rtc_ice_candidate.sdpMLineIndex = sdpMLineIndex
            log.info('RTCIceCandidate: %r', rtc_ice_candidate)
            log.info('peerConnection: %r', peerConnection)
            peerConnection.addIceCandidate(rtc_ice_candidate)
            log.info('Added ICE candidate for peer %s',
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
