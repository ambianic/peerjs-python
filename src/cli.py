"""Register with PNP server and wait for remote peers to connect."""
import argparse
import asyncio
import logging
import time
from .peerroom import PeerRoom
from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription
from .pnpsignaling import AmbianicPnpSignaling

log = logging.getLogger(__name__)


def _server_register(channel, t, message):
    """Register this peer with signaling server."""
    print('Registering this client with peer discovery server')


def _room_join(channel, t, message):
    """Join room with other local network peers to allow auto discovery."""
    print('Joining room with local network peers')


def _channel_log(channel, t, message):
    print("channel(%s) %s %s" % (channel.label, t, message))


def _channel_send(channel, message):
    _channel_log(channel, ">", message)
    channel.send(message)


async def _consume_signaling(pc, signaling):
    while True:
        obj = await signaling.receive()

        if isinstance(obj, RTCSessionDescription):
            await pc.setRemoteDescription(obj)

            if obj.type == "offer":
                # send answer
                await pc.setLocalDescription(await pc.createAnswer())
                await signaling.send(pc.localDescription)
        elif isinstance(obj, RTCIceCandidate):
            pc.addIceCandidate(obj)
        elif obj is None:
            print("Exiting")
            break

time_start = None


def _current_stamp():
    global time_start
    if time_start is None:
        time_start = time.time()
        return 0
    else:
        return int((time.time() - time_start) * 1000000)


async def _run_answer(pc, signaling):
    await signaling.connect()
    @pc.on("datachannel")
    def on_datachannel(channel):
        _channel_log(channel, "-", "created by remote party")
        @channel.on("message")
        def on_message(message):
            _channel_log(channel, "<", message)
            if isinstance(message, str) and message.startswith("ping"):
                # reply
                _channel_send(channel, "pong" + message[4:])
    await _consume_signaling(pc, signaling)


async def _run_offer(pc, signaling):
    await signaling.connect()
    channel = pc.createDataChannel("chat")
    _channel_log(channel, "-", "created by local party")

    async def send_pings():
        while True:
            _channel_send(channel, "ping %d" % _current_stamp())
            await asyncio.sleep(1)

    @channel.on("open")
    def on_open():
        asyncio.ensure_future(send_pings())

    @channel.on("message")
    def on_message(message):
        _channel_log(channel, "<", message)
        if isinstance(message, str) and message.startswith("pong"):
            elapsed_ms = (_current_stamp() - int(message[5:])) / 1000
            print(" RTT %.2f ms" % elapsed_ms)

    # send offer
    await pc.setLocalDescription(await pc.createOffer())
    await signaling.send(pc.localDescription)
    await _consume_signaling(pc, signaling)

myPeerId = None
remotePeerId = None


async def discoverRemotePeerId(peer=None):
    """Try to find a remote peer in the same local room."""
    global remotePeerId
    if not remotePeerId:
        # first try to find the remote peer ID in the same room
        myRoom = PeerRoom(peer)
        log.debug('Fetching room members', myRoom)
        peerIds = await myRoom.getRoomMembers()
        log.debug('myRoom members', peerIds)
        try:
            remotePeerId = [pid for pid in peerIds if pid != myPeerId][0]
            return remotePeerId
        except IndexError:
            # no other peers in room
            return None
    else:
        return remotePeerId

if __name__ == "__main__":
    args = None
    parser = argparse.ArgumentParser(description="Data channels ping/pong")
    parser.add_argument("role", choices=["offer", "answer"])
    parser.add_argument("--verbose", "-v", action="count")
    # add_signaling_arguments(parser)
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    # signaling = create_signaling(args)
    signaling = AmbianicPnpSignaling(args)
    pc = RTCPeerConnection()
    if args.role == "offer":
        coro = _run_offer(pc, signaling)
    else:
        coro = _run_answer(pc, signaling)
    # run event loop
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(coro)
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(pc.close())
        loop.run_until_complete(signaling.close())
