"""Constructs for managing negotiations between Peers."""
from util import util
from pyee import BaseEventEmitter
import logging
# import { MediaConnection } from "./mediaconnection";
from .dataconnection import DataConnection
from enums import \
    ConnectionType, \
    PeerErrorType, \
    ConnectionEventType, \
    ServerMessageType
from .baseconnection import BaseConnection
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate

log = logging.getLogger(__name__)


class Negotiator:
    """Manages all negotiations between Peers."""

    def __init__(self, connection: BaseConnection = None):
        """Create negotiator."""

    def startConnection(self, options=None) -> RTCPeerConnection:
        """Return a PeerConnection object setup correctly for data or media."""
        peerConnection = self._startPeerConnection()
        # Set the connection wrapper's RTCPeerConnection.
        self.connection.peerConnection = peerConnection
        if self.connection.type == ConnectionType.Media and options._stream:
            self._addTracksToConnection(options._stream, peerConnection)
        # What do we need to do now?
        if options.originator:
            # originate connection offer
            if self.connection.type == ConnectionType.Data:
                dataConnection: DataConnection = self.connection
                # Pass RTCDataChannelInit dictionary
                # https://developer.mozilla.org/en-US/docs/Web/API/RTCPeerConnection/createDataChannel#RTCDataChannelInit_dictionary
                config = {'ordered': options.reliable}
                dataChannel = peerConnection.createDataChannel(
                    dataConnection.label,
                    config)
                dataConnection.initialize(dataChannel)
            self._makeOffer()
        else:
            # receive connection offer originated by remote peer
            self.handleSDP("OFFER", options.sdp)

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
                log.debug(
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
                log.debug(
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
                log.debug(
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
            log.debug("Received data channel.")
            dataChannel = evt.channel
            connection = provider.getConnection(peerId, connectionId)
            connection.initialize(dataChannel)

        # MEDIACONNECTION.
        log.debug("Listening for remote stream.")
        @peerConnection.on("track")
        def peerconn_ontrack(evt):
            log.debug("Received remote stream.")
            stream = evt.streams[0]
            connection = provider.getConnection(peerId, connectionId)
            if connection.type == ConnectionType.Media:
                mediaConnection = connection
                self._addStreamToMediaConnection(stream, mediaConnection)

    def cleanup(self) -> None:
        """Clean up resources after connection closes."""
        log.debug("Cleaning up PeerConnection to {}", self.connection.peer)
        peerConnection = self.connection.peerConnection
        if not peerConnection:
            return
        self.connection.peerConnection = None
        # unsubscribe from all PeerConnection's events
        peerConnection.remove_all_listeners()
        peerConnectionNotClosed = peerConnection.signalingState != "closed"
        dataChannelNotClosed = False
        if self.connection.type == ConnectionType.Data:
            dataConnection: DataConnection = self.connection
            dataChannel = dataConnection.dataChannel
            if dataChannel:
                dataChannelNotClosed = dataChannel.readyState and \
                    dataChannel.readyState != "closed"
        if peerConnectionNotClosed or dataChannelNotClosed:
            peerConnection.close()

    async def _makeOffer(self):
        peerConnection = self.connection.peerConnection
        provider = self.connection.provider
        try:
            offer = await peerConnection.createOffer(
                self.connection.options.constraints)
            log.debug("Created offer.")

            if self.connection.options.sdpTransform and \
               callable(self.connection.options.sdpTransform):
                tSDP = self.connection.options.sdpTransform(offer.sdp)
                if tSDP:
                    offer.sdp = tSDP
            try:
                await peerConnection.setLocalDescription(offer)
                log.debug(f"Set localDescription:{offer} "
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
            log.debug("Created answer.")
            if self.connection.options.sdpTransform and \
               callable(self.connection.options.sdpTransform):
                answer.sdp = self.connection.options.sdpTransform(answer.sdp) \
                    or answer.sdp
            try:
                await peerConnection.setLocalDescription(answer)
                log.debug(f"Set localDescription: {answer}"
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
                log.debug("Failed to setLocalDescription, ", err)
        except Exception as err_1:
            provider.emitError(PeerErrorType.WebRTC, err_1)
            log.debug("Failed to create answer, ", err_1)

    async def handleSDP(self, _type: str = None, sdp: any = None) -> None:
        """Handle an SDP."""
        sdp = RTCSessionDescription(sdp)
        peerConnection = self.connection.peerConnection
        provider = self.connection.provider
        log.debug("Setting remote description", sdp)
        try:
            await peerConnection.setRemoteDescription(sdp)
            log.debug(f'Set remoteDescription:{type} '
                      f'for:{self.connection.peer}')
            if _type == "OFFER":
                await self._makeAnswer()
        except Exception as err:
            provider.emitError(PeerErrorType.WebRTC, err)
            log.debug("Failed to setRemoteDescription, ", err)

    async def handleCandidate(self, ice=None):
        """Handle new peer candidate."""
        log.debug(f'handleCandidate:', ice)
        candidate = ice.candidate
        sdpMLineIndex = ice.sdpMLineIndex
        sdpMid = ice.sdpMid
        peerConnection = self.connection.peerConnection
        provider = self.connection.provider
        try:
            await peerConnection.addIceCandidate(
                RTCIceCandidate({
                    'sdpMid': sdpMid,
                    'sdpMLineIndex': sdpMLineIndex,
                    'candidate': candidate
                    })
                )
            log.debug(f'Added ICE candidate for:{self.connection.peer}')
        except Exception as err:
            provider.emitError(PeerErrorType.WebRTC, err)
            log.debug("Failed to handleCandidate, ", err)

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
