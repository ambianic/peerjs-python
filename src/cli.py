"""Register with PNP server and wait for remote peers to connect."""

import argparse
import asyncio
import logging
import time

from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.signaling import add_signaling_arguments, create_signaling


def _server_register(channel, t, message):
    """Register this peer with PNP server."""
    print('Registering this client with peer discovery server')


def _room_join(channel, t, message):
    """Join room with other local network peers to allow auto discovery."""
    print('Joining room with local network peers')


def _channel_log(channel, t, message):
    print("channel(%s) %s %s" % (channel.label, t, message))


def _channel_send(channel, message):
    _channel_log(channel, ">", message)
    channel.send(message)


def @ps.on("message")
async def handle_signal():
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

async function discoverRemotePeerId ({ peer, state, commit }) {
  if (!state.remotePeerId) {
    // first try to find the remote peer ID in the same room
    const myRoom = new PeerRoom(peer)
    console.log('Fetching room members', myRoom)
    const peerIds = [] // await myRoom.getRoomMembers()
    console.log('myRoom members', peerIds)
    const remotePeerId = peerIds.find(
      pid => pid !== state.myPeerId)
    if (remotePeerId) {
      return remotePeerId
    } else {
      // unable to auto discover
      // ask user for help
      commit(USER_MESSAGE,
        `Still looking.
         Please make sure you are are on the same local network.
        `)
    }
  } else {
    return state.remotePeerId
  }
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Data channels ping/pong")
    parser.add_argument("role", choices=["offer", "answer"])
    parser.add_argument("--verbose", "-v", action="count")
    add_signaling_arguments(parser)
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    signaling = create_signaling(args)
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
