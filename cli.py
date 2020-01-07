"""Register with PNP server and wait for remote peers to connect."""
# import argparse
import asyncio
import logging
import sys

# from aiortc import RTCIceCandidate, RTCSessionDescription
from peerjs.peer import Peer, PeerOptions
from peerjs.peerroom import PeerRoom

print(sys.version)

log = logging.getLogger(__name__)

peer = None
myPeerId = None
AMBIANIC_PNP_HOST = 'ambianic-pnp.herokuapp.com'
AMBIANIC_PNP_PORT = 443
AMBIANIC_PNP_SECURE = True
time_start = None
peerConnectionStatus = None
discoveryLoop = None


# async def _consume_signaling(pc, signaling):
#     while True:
#         obj = await signaling.receive()
#         if isinstance(obj, RTCSessionDescription):
#             await pc.setRemoteDescription(obj)
#             if obj.type == "offer":
#                 # send answer
#                 await pc.setLocalDescription(await pc.createAnswer())
#                 await signaling.send(pc.localDescription)
#         elif isinstance(obj, RTCIceCandidate):
#             pc.addIceCandidate(obj)
#         elif obj is None:
#             print("Exiting")
#             break


async def join_peer_room(peer=None):
    """Join a peer room with other local peers."""
    # first try to find the remote peer ID in the same room
    assert peer
    myRoom = PeerRoom(peer)
    log.info('Fetching room members %s', myRoom.id)
    peerIds = await myRoom.getRoomMembers()
    log.info('myRoom members %r', peerIds)


def _setPnPServiceConnectionHandlers(peer=None):
    global myPeerId
    @peer.on('open')
    async def peer_open(id):
        global myPeerId
        # Workaround for peer.reconnect deleting previous id
        if peer.id is None:
            log.warning('pnpService: Received null id from peer open')
            peer.id = myPeerId
        else:
            if myPeerId != peer.id:
                log.info(
                    'pnpService: Service returned new peerId. Old %s, New %s',
                    myPeerId,
                    peer.id
                    )
            myPeerId = peer.id
        log.info('pnpService: myPeerId: ', peer.id)

    @peer.on('disconnected')
    async def peer_disconnected():
        global myPeerId
        log.info('pnpService: Connection lost. Please reconnect')
        # Workaround for peer.reconnect deleting previous id
        if not peer.id:
            log.info('BUG WORKAROUND: Peer lost ID. '
                     'Resetting to last known ID.')
            peer._id = myPeerId
        peer._lastServerId = myPeerId
        peer.reconnect()

    @peer.on('close')
    def peer_close():
        # peerConnection = null
        log.info('pnpService: Connection closed')

    @peer.on('error')
    def peer_error(err):
        log.warning('pnpService %s', err)
        log.info('peerConnectionStatus', peerConnectionStatus)
        # retry peer connection in a few seconds
        asyncio.call_later(3, pnp_service_connect)

    # remote peer tries to initiate connection
    @peer.on('connection')
    async def peer_connection(peerConnection):
        log.info('remote peer trying to establish connection')
        _setPeerConnectionHandlers(peerConnection)


def _setPeerConnectionHandlers(peerConnection):
    @peerConnection.on('open')
    async def pc_open():
        log.info('pnpService: Connected to: %s', peerConnection.peer)

    # Handle incoming data (messages only since this is the signal sender)
    @peerConnection.on('data')
    async def pc_data(data):
        log.info('pnpService: data received from remote peer %r', data)
        pass

    @peerConnection.on('close')
    async def pc_close():
        log.info('Connection to remote peer closed')


# async def _run_answer(pc, signaling):
#     await signaling.connect()
#     @pc.on("datachannel")
#     def on_datachannel(channel):
#         _channel_log(channel, "-", "created by remote party")
#         @channel.on("message")
#         def on_message(message):
#             _channel_log(channel, "<", message)
#             if isinstance(message, str) and message.startswith("ping"):
#                 # reply
#                 _channel_send(channel, "pong" + message[4:])
#     await _consume_signaling(pc, signaling)

async def pnp_service_connect() -> Peer:
    """Create a Peer instance and register with PnP signaling server."""
    # if connection to pnp service already open, then nothing to do
    global peer
    if peer and peer.open:
        log.info('peer already connected')
        return
    # Create own peer object with connection to shared PeerJS server
    log.info('pnpService: creating peer')
    # If we already have an assigned peerId, we will reuse it forever.
    # We expect that peerId is crypto secure. No need to replace.
    # Unless the user explicitly requests a refresh.
    global myPeerId
    log.info('pnpService: last saved myPeerId %s', myPeerId)
    options = PeerOptions(
        host=AMBIANIC_PNP_HOST,
        port=AMBIANIC_PNP_PORT,
        secure=AMBIANIC_PNP_SECURE
    )
    peer = Peer(id=myPeerId, peer_options=options)
    log.info('pnpService: peer created')
    await peer.start()
    log.info('pnpService: peer activated')
    _setPnPServiceConnectionHandlers(peer)
    await make_discoverable(peer=peer)


async def make_discoverable(peer=None):
    """Enable remote peers to find and connect to this peer."""
    assert peer
    while True:
        log.info('Making peer discoverable.')
        try:
            await join_peer_room(peer=peer)
        except Exception as e:
            log.warning('Unable to join room. '
                        'Will retry in a few seconds. '
                        'Error %r', e)
        await asyncio.sleep(5)


def _config_logger():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    format_cfg = '%(asctime)s %(levelname)-4s ' \
        '%(pathname)s.%(funcName)s(%(lineno)d): %(message)s'
    datefmt_cfg = '%Y-%m-%d %H:%M:%S'
    fmt = logging.Formatter(fmt=format_cfg,
                            datefmt=datefmt_cfg, style='%')
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root_logger.handlers = []
    root_logger.addHandler(ch)


if __name__ == "__main__":
    # args = None
    # parser = argparse.ArgumentParser(description="Data channels ping/pong")
    # parser.add_argument("role", choices=["offer", "answer"])
    # parser.add_argument("--verbose", "-v", action="count")
    # add_signaling_arguments(parser)
    # args = parser.parse_args()
    # if args.verbose:
    _config_logger()
    # add formatter to ch
    log.debug('Log level set to debug')
    # signaling = create_signaling(args)
    # signaling = AmbianicPnpSignaling(args)
    # pc = RTCPeerConnection()
    # if args.role == "offer":
    #     coro = _run_offer(pc, signaling)
    # else:
    #     coro = _run_answer(pc, signaling)
    coro = pnp_service_connect()
    # run event loop
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(coro)
    except KeyboardInterrupt:
        log.info('KeyboardInterrupt detected. Exiting...')
        pass
    finally:
        if peer:
            loop.run_until_complete(peer.destroy())
        # loop.run_until_complete(pc.close())
        # loop.run_until_complete(signaling.close())
