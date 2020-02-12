"""Register with PNP server and wait for remote peers to connect."""
# import argparse
import asyncio
import logging
import sys
import json
import requests
from typing import Any
import coloredlogs
from pathlib import Path

# from aiortc import RTCIceCandidate, RTCSessionDescription
from peerjs.peer import Peer, PeerOptions
from peerjs.peerroom import PeerRoom
from peerjs.util import util
from peerjs.enums import ConnectionEventType, PeerEventType

print(sys.version)

log = logging.getLogger(__name__)

LOG_LEVEL = logging.INFO

peer = None
savedPeerId = None
# persisted config dict
config = {}
CONFIG_FILE = '.peerjsrc'
AMBIANIC_PNP_HOST = 'ambianic-pnp.herokuapp.com'  # 'localhost'
AMBIANIC_PNP_PORT = 443  # 9779
AMBIANIC_PNP_SECURE = True  # False
time_start = None
peerConnectionStatus = None
discoveryLoop = None

# flags when user requests shutdown
# via CTRL+C or another system signal
_is_shutting_down: bool = False


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
    myRoom = PeerRoom(peer)
    log.debug('Fetching room members...')
    peerIds = await myRoom.getRoomMembers()
    log.info('myRoom members %r', peerIds)


def _savePeerId(peerId=None):
    assert peerId
    global savedPeerId
    savedPeerId = peerId
    config['peerId'] = peerId
    with open(CONFIG_FILE, 'w') as outfile:
        json.dump(config, outfile)


def _loadConfig():
    global config
    global savedPeerId
    conf_file = Path(CONFIG_FILE)
    if conf_file.exists():
        with conf_file.open() as infile:
            config = json.load(infile)
        savedPeerId = config.get('peerId', None)


def _setPnPServiceConnectionHandlers(peer=None):
    assert peer
    global savedPeerId
    @peer.on(PeerEventType.Open)
    async def peer_open(id):
        log.info('Peer signaling connection open.')
        global savedPeerId
        # Workaround for peer.reconnect deleting previous id
        if peer.id is None:
            log.info('pnpService: Received null id from peer open')
            peer.id = savedPeerId
        else:
            if savedPeerId != peer.id:
                log.info(
                    'PNP Service returned new peerId. Old %s, New %s',
                    savedPeerId,
                    peer.id
                    )
            _savePeerId(peer.id)
        log.info('savedPeerId: %s', peer.id)

    @peer.on(PeerEventType.Disconnected)
    async def peer_disconnected(peerId):
        global savedPeerId
        log.info('Peer %s disconnected from server.', peerId)
        # Workaround for peer.reconnect deleting previous id
        if not peer.id:
            log.debug('BUG WORKAROUND: Peer lost ID. '
                      'Resetting to last known ID.')
            peer._id = savedPeerId
        peer._lastServerId = savedPeerId
        global _is_shutting_down
        if not _is_shutting_down:
            await peer.reconnect()

    @peer.on(PeerEventType.Close)
    def peer_close():
        # peerConnection = null
        log.info('Peer connection closed')

    @peer.on(PeerEventType.Error)
    def peer_error(err):
        log.exception('Peer error %s', err)
        log.warning('peerConnectionStatus %s', peerConnectionStatus)
        # retry peer connection in a few seconds
        # loop = asyncio.get_event_loop()
        # loop.call_later(3, pnp_service_connect)

    # remote peer tries to initiate connection
    @peer.on(PeerEventType.Connection)
    async def peer_connection(peerConnection):
        log.info('Remote peer trying to establish connection')
        _setPeerConnectionHandlers(peerConnection)


async def _fetch(url: str = None, method: str = 'GET') -> Any:
    if method == 'GET':
        response = requests.get(url)
        # response_content = {'name': 'Ambianic-Edge', 'version': '1.24.2020'}
        # rjson = json.dumps(response_content)
        return response
    else:
        raise NotImplementedError(
            f'HTTP method ${method} not implemented.'
            ' Contributions welcome!')


async def _pong(peerConnection):
    response_header = {
        'status': 200,
    }
    header_as_json = json.dumps(response_header)
    log.debug('sending keepalive pong back to remote peer')
    await peerConnection.send(header_as_json)
    await peerConnection.send('pong')


def _setPeerConnectionHandlers(peerConnection):

    @peerConnection.on(ConnectionEventType.Open)
    async def pc_open():
        log.info('Connected to: %s', peerConnection.peer)

    # Handle incoming data (messages only since this is the signal sender)
    @peerConnection.on(ConnectionEventType.Data)
    async def pc_data(data):
        log.debug('data received from remote peer \n%r', data)
        request = json.loads(data)
        # check if the request is just a keepalive ping
        if (request['url'].startswith('ping')):
            log.debug('received keepalive ping from remote peer')
            await _pong(peerConnection=peerConnection)
            return
        log.info('webrtc peer: http proxy request: \n%r', request)
        # schedule frequent pings while waiting on response_header
        # to keep the peer data channel open
        waiting_on_fetch = asyncio.Event()

        async def ping(stop_flag=None):
            while not stop_flag.is_set():
                # send HTTP 202 Accepted status code to inform
                # client that we are still waiting on the http
                # server to complete its response
                ping_as_json = json.dumps({'status': 202})
                await peerConnection.send(ping_as_json)
                log.info('webrtc peer: http proxy response ping. '
                         'Keeping datachannel alive.')
                await asyncio.sleep(1)

        asyncio.create_task(ping(waiting_on_fetch))
        response = None
        try:
            response = await _fetch(**request)
        except Exception as e:
            log.exception('Error %s while fetching response'
                          ' with request: \n %r',
                          e, request)
        finally:
            # fetch completed, cancel pings
            waiting_on_fetch.set()
        if not response:
            response_header = {
                # internal server error code
                'status': 500
            }
            response_content = None
            return
        response_content = response.content
        response_header = {
            'status': response.status_code,
            'content-type': response.headers['content-type'],
            'encoding': response.encoding,
            'content-length': len(response_content)
        }
        log.info('Answering request: \n%r '
                 'response header: \n %r',
                 request, response_header)
        header_as_json = json.dumps(response_header)
        await peerConnection.send(header_as_json)
        await peerConnection.send(response_content)

    @peerConnection.on(ConnectionEventType.Close)
    async def pc_close():
        log.info('Connection to remote peer closed')


async def pnp_service_connect() -> Peer:
    """Create a Peer instance and register with PnP signaling server."""
    # if connection to pnp service already open, then nothing to do
    global peer
    if peer and peer.open:
        log.info('peer already connected')
        return
    # Create own peer object with connection to shared PeerJS server
    log.info('creating peer')
    # If we already have an assigned peerId, we will reuse it forever.
    # We expect that peerId is crypto secure. No need to replace.
    # Unless the user explicitly requests a refresh.
    global savedPeerId
    log.info('last saved savedPeerId %s', savedPeerId)
    new_token = util.randomToken()
    log.info('Peer session token %s', new_token)
    options = PeerOptions(
        host=AMBIANIC_PNP_HOST,
        port=AMBIANIC_PNP_PORT,
        secure=AMBIANIC_PNP_SECURE,
        token=new_token
    )
    peer = Peer(id=savedPeerId, peer_options=options)
    log.info('pnpService: peer created with id %s , options: %r',
             peer.id,
             peer.options)
    await peer.start()
    log.info('peer activated')
    _setPnPServiceConnectionHandlers(peer)
    log.info('Calling make_discoverable')
    await make_discoverable(peer=peer)
    log.info('Exited make_discoverable')


async def make_discoverable(peer=None):
    """Enable remote peers to find and connect to this peer."""
    log.debug('Enter peer discoverable.')
    assert peer
    log.debug('Before _is_shutting_down')
    global _is_shutting_down
    log.debug('Making peer discoverable.')
    while not _is_shutting_down:
        log.debug('Discovery loop.')
        try:
            # check if the websocket connection
            # to the signaling server is alive
            if peer.open:
                await join_peer_room(peer=peer)
            else:
                log.info('Peer not connected to signaling server. '
                         'Will retry in a bit.')
                if peer.disconnected:
                    log.info('Peer disconnected. Will try to reconnect.')
                    await peer.reconnect()
                else:
                    log.info('Peer still establishing connection. %r', peer)
        except Exception as e:
            log.exception('Unable to join room. '
                          'Will retry in a few moments. '
                          'Error %r', e)
        await asyncio.sleep(3)


def _config_logger():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    format_cfg = '%(asctime)s %(levelname)-4s ' \
        '%(pathname)s.%(funcName)s(%(lineno)d): %(message)s'
    datefmt_cfg = '%Y-%m-%d %H:%M:%S'
    fmt = logging.Formatter(fmt=format_cfg,
                            datefmt=datefmt_cfg, style='%')
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(LOG_LEVEL)
    ch.setFormatter(fmt)
    root_logger.handlers = []
    root_logger.addHandler(ch)
    coloredlogs.install(level=LOG_LEVEL, fmt=format_cfg)


def _shutdown():
    global _is_shutting_down
    _is_shutting_down = True
    loop = asyncio.get_event_loop()
    if peer:
        loop.run_until_complete(peer.destroy())
    # loop.run_until_complete(pc.close())
    # loop.run_until_complete(signaling.close())
    loop.close()


if __name__ == "__main__":
    # args = None
    # parser = argparse.ArgumentParser(description="Data channels ping/pong")
    # parser.add_argument("role", choices=["offer", "answer"])
    # parser.add_argument("--verbose", "-v", action="count")
    # add_signaling_arguments(parser)
    # args = parser.parse_args()
    # if args.verbose:
    _loadConfig()
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
    coro = pnp_service_connect
    # run event loop
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(coro())
        loop.run_forever()
    except KeyboardInterrupt:
        log.info('KeyboardInterrupt detected.')
    finally:
        log.info('Shutting down...')
        _shutdown()
