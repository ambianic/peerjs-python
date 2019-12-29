"""Constructs for managing negotiations between Peers."""
from util import util
import logging
# import { MediaConnection } from "./mediaconnection";
from .dataconnection import DataConnection
from enums import \
    ConnectionType, \
    PeerErrorType, \
    ConnectionEventType, \
    ServerMessageType
from .baseconnection import BaseConnection

class Negotiator:
    """Manages all negotiations between Peers."""

    def __init__(self, connection: BaseConnection = None):
        """Create negotiator."""

    def startConnection(options=None) -> RTCPeerConnection:
        """Return a PeerConnection object set up correctly (for data, media)."""
        peerConnection = self._startPeerConnection()

        # Set the connection wrapper's RTCPeerConnection.
        this.connection.peerConnection = peerConnection

        if self.connection.type == ConnectionType.Media and options._stream:
            self._addTracksToConnection(options._stream, peerConnection)

        # What do we need to do now?
        if options.originator:
            # originate connection offer
            if this.connection.type == ConnectionType.Data:
                dataConnection = this.connection
                config: RTCDataChannelInit = { 'ordered': options.reliable }
                dataChannel = peerConnection.createDataChannel(
                    dataConnection.label,
                    config)
                dataConnection.initialize(dataChannel)
            self._makeOffer()
        else:
            # receive connection offer originated by remote peer
            self.handleSDP("OFFER", options.sdp);

    def _startPeerConnection() -> RTCPeerConnection:
        """Start a Peer Connection."""
        log.debug("Creating RTCPeerConnection.")
        peerConnection = RTCPeerConnection(this.connection.provider.options.config)
        self._setupListeners(peerConnection)
        return peerConnection

    def _setupListeners(peerConnection: RTCPeerConnection = None):
        """Set up various WebRTC listeners."""
        peerId = this.connection.peer
        connectionId = this.connection.connectionId
        connectionType = this.connection.type
        provider = this.connection.provider

        # ICE CANDIDATES.
        log.debug("Listening for ICE candidates.")
        # Its not clear how aiortc supports trickle ice.
        # Track issue: https://github.com/aiortc/aiortc/issues/246
        # def peerconn_onicecandidate
        # peerConnection.onicecandidate = (evt) => {
        #     if (!evt.candidate || !evt.candidate.candidate) return;
        #
        #     logger.log(`Received ICE candidates for ${peerId}:`, evt.candidate);
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
                logger.log(
                    "iceConnectionState is failed, closing connections to " +
                    peerId
                    )
                self.connection.emit(
                    ConnectionEventType.Error,
                    ConnectionError("Negotiation of connection to " + peerId + " failed.")
                    )
                self.connection.close()

            @state_change.once("closed")
            def on_closed():
                log.debug(
                    "iceConnectionState is closed, closing connections to " +
                    peerId
                    )
                self.connection.emit(
                    ConnectionEventType.Error,
                    ConnectionError("Connection to " + peerId + " closed.")
                    )
                self.connection.close()

            @state_change.once("disconnected")
            def on_disconnected():
                logger.log(
                    "iceConnectionState is disconnected, closing connections to " +
                    peerId
                    )
                self.connection.emit(
                    ConnectionEventType.Error,
                    ConnectionError("Connection to " + peerId + " disconnected.")
                    )
                self.connection.close()

            @state_change.once("completed")
            def on_completed():
                # this function needs to be implemented as in PeerJS
                # https://github.com/peers/peerjs/blob/5e36ba17be02a9af7c171399f7737d8ccb38fbbe/lib/negotiator.ts#L119
                # when the "icecandidate"
                # event handling issue above is resolved
                # peerConnection.remove_listener("icecandidate", peerconn_onicecandidate)
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
        @pc.on("datachannel")
        def peerconn_ondatachanel(evt):
            log.debug("Received data channel.")
            dataChannel = evt.channel
            connection = provider.getConnection(peerId, connectionId)
            connection.initialize(dataChannel)

        # MEDIACONNECTION.
        log.debug("Listening for remote stream.")
        @pc.on("track")
        def peerconn_ontrack(evt):
            log.debug("Received remote stream.")
            stream = evt.streams[0]
            connection = provider.getConnection(peerId, connectionId)
            if connection.type == ConnectionType.Media:
                mediaConnection = connection
                self._addStreamToMediaConnection(stream, mediaConnection)

    def cleanup() -> None:
        log.debug("Cleaning up PeerConnection to " + this.connection.peer)
        peerConnection = this.connection.peerConnection
        if not peerConnection:
            return
        self.connection.peerConnection = None
        # unsubscribe from all PeerConnection's events
        peerConnection.remove_all_listeners()
        peerConnectionNotClosed = peerConnection.signalingState != "closed"
        dataChannelNotClosed = False
        if self.connection.type == ConnectionType.Data:
            dataConnection = self.connection
            dataChannel = dataConnection.dataChannel
            if dataChannel:
                dataChannelNotClosed = dataChannel.readyState and \
                    dataChannel.readyState != "closed"
        if peerConnectionNotClosed or dataChannelNotClosed:
            peerConnection.close()

    async def _makeOffer():
        peerConnection = this.connection.peerConnection
        provider = this.connection.provider
        try:
            offer = await peerConnection.createOffer(
                this.connection.options.constraints)
            log.debug("Created offer.")

            if self.connection.options.sdpTransform and \
                 callable(self.connection.options.sdpTransform):
                offer.sdp = self.connection.options.sdpTransform(offer.sdp) or offer.sdp

            try:
                await peerConnection.setLocalDescription(offer)
                log.debug(f"Set localDescription:{offer} for: {self.connection.peer}")

                payload: {
          sdp: offer,
          type: this.connection.type,
          connectionId: this.connection.connectionId,
          metadata: this.connection.metadata,
          browser: util.browser
        };

        if (this.connection.type === ConnectionType.Data) {
          const dataConnection = <DataConnection>this.connection;

          payload = {
            ...payload,
            label: dataConnection.label,
            reliable: dataConnection.reliable,
            serialization: dataConnection.serialization
          };
        }

        provider.socket.send({
          type: ServerMessageType.Offer,
          payload,
          dst: this.connection.peer
        });
      } catch (err) {
        // TODO: investigate why _makeOffer is being called from the answer
        if (
          err !=
          "OperationError: Failed to set local offer sdp: Called in wrong state: kHaveRemoteOffer"
        ) {
          provider.emitError(PeerErrorType.WebRTC, err);
          logger.log("Failed to setLocalDescription, ", err);
        }
      }
    } catch (err_1) {
      provider.emitError(PeerErrorType.WebRTC, err_1);
      logger.log("Failed to createOffer, ", err_1);
    }
  }

  private async _makeAnswer(): Promise<void> {
    const peerConnection = this.connection.peerConnection;
    const provider = this.connection.provider;

    try {
      const answer = await peerConnection.createAnswer();
      logger.log("Created answer.");

      if (this.connection.options.sdpTransform && typeof this.connection.options.sdpTransform === 'function') {
        answer.sdp = this.connection.options.sdpTransform(answer.sdp) || answer.sdp;
      }

      try {
        await peerConnection.setLocalDescription(answer);

        logger.log(`Set localDescription:`, answer, `for:${this.connection.peer}`);

        provider.socket.send({
          type: ServerMessageType.Answer,
          payload: {
            sdp: answer,
            type: this.connection.type,
            connectionId: this.connection.connectionId,
            browser: util.browser
          },
          dst: this.connection.peer
        });
      } catch (err) {
        provider.emitError(PeerErrorType.WebRTC, err);
        logger.log("Failed to setLocalDescription, ", err);
      }
    } catch (err_1) {
      provider.emitError(PeerErrorType.WebRTC, err_1);
      logger.log("Failed to create answer, ", err_1);
    }
  }

  /** Handle an SDP. */
  async handleSDP(
    type: string,
    sdp: any
  ): Promise<void> {
    sdp = new RTCSessionDescription(sdp);
    const peerConnection = this.connection.peerConnection;
    const provider = this.connection.provider;

    logger.log("Setting remote description", sdp);

    const self = this;

    try {
      await peerConnection.setRemoteDescription(sdp);
      logger.log(`Set remoteDescription:${type} for:${this.connection.peer}`);
      if (type === "OFFER") {
        await self._makeAnswer();
      }
    } catch (err) {
      provider.emitError(PeerErrorType.WebRTC, err);
      logger.log("Failed to setRemoteDescription, ", err);
    }
  }

  /** Handle a candidate. */
  async handleCandidate(ice: any): Promise<void> {
    logger.log(`handleCandidate:`, ice);

    const candidate = ice.candidate;
    const sdpMLineIndex = ice.sdpMLineIndex;
    const sdpMid = ice.sdpMid;
    const peerConnection = this.connection.peerConnection;
    const provider = this.connection.provider;

    try {
      await peerConnection.addIceCandidate(
        new RTCIceCandidate({
          sdpMid: sdpMid,
          sdpMLineIndex: sdpMLineIndex,
          candidate: candidate
        })
      );
      logger.log(`Added ICE candidate for:${this.connection.peer}`);
    } catch (err) {
      provider.emitError(PeerErrorType.WebRTC, err);
      logger.log("Failed to handleCandidate, ", err);
    }
  }

  private _addTracksToConnection(
    stream: MediaStream,
    peerConnection: RTCPeerConnection
  ): void {
    logger.log(`add tracks from stream ${stream.id} to peer connection`);

    if (!peerConnection.addTrack) {
      return logger.error(
        `Your browser does't support RTCPeerConnection#addTrack. Ignored.`
      );
    }

    stream.getTracks().forEach(track => {
      peerConnection.addTrack(track, stream);
    });
  }

  private _addStreamToMediaConnection(
    stream: MediaStream,
    mediaConnection: MediaConnection
  ): void {
    logger.log(
      `add stream ${stream.id} to media connection ${
      mediaConnection.connectionId
      }`
    );

    mediaConnection.addStream(stream);
  }
}
