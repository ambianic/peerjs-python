"""Peer side signaling logic."""
import asyncio
import json
import logging
import aiohttp
import websockets
from pyee import AsyncIOEventEmitter
from aiortc import RTCIceCandidate, RTCSessionDescription
from aiortc.sdp import candidate_from_sdp, candidate_to_sdp

logger = logging.getLogger("aiortc.contrib.signaling")


class PeerSignaling(AsyncIOEventEmitter):
    """Manage signaling between peer and signaling server."""

    def __init__(self, room):
        """Configure connection."""
        self._http = None
        self._origin = "https://ambianic-pnp.herokuapp.com"
        self._room = room
        self._websocket = None
        self._peerId = None
        self._roomId = None

    async def _getPeerId(self):
        join_url = self._origin + "/id/" + self._room
        assert self._http
        # fetch room parameters
        async with self._http.post(join_url) as response:
            # we cannot use response.json() due to:
            # https://github.com/webrtc/apprtc/issues/562
            data = json.loads(await response.text())
        assert data["result"] == "SUCCESS"
        params = data["params"]

        self.__is_initiator = params["is_initiator"] == "true"
        self.__post_url = (
            self._origin + "/message/" + self._room + "/" + params["client_id"]
        )

    async def _joinRoom(self):
        join_url = self._origin + "/id/" + self._room
        assert self._http
        # fetch room parameters
        async with self._http.post(join_url) as response:
            # we cannot use response.json() due to:
            # https://github.com/webrtc/apprtc/issues/562
            data = json.loads(await response.text())
        assert data["result"] == "SUCCESS"
        params = data["params"]

        self.__is_initiator = params["is_initiator"] == "true"
        self.__post_url = (
            self._origin + "/message/" + self._room + "/" + params["client_id"]
        )

    async def connect(self):
        """Connect to server."""
        self._http = aiohttp.ClientSession()
        self._peerId = await self._getPeerId()
        await self._joinRoom()

        # start websocket connection
        self._socket = Socket(wss_url = params["wss_url"], origin = self._origin)
        self._socket.start()

        print("Ambianic PnP room is %(room_id)s %(room_link)s" % params)

        return params

    async def close(self):
        if self._websocket:
            await self.send(None)
            await self._websocket.close()
        if self._http:
            await self._http.close()

    async def send(self, obj):
        """Send a signaling message through the server."""
        message = _object_to_string(obj)
        logger.info("> " + message)
        if self.__is_initiator:
            await self._http.post(self.__post_url, data=message)
        else:
            await self._websocket.send(json.dumps({
                "cmd": "send", "msg": message}))

    async def start(self):
        """Start the signaling loop.

        Run until stop() is called or the connection is broken.
        """
        while not self._end_signaling_loop.isSet():
            obj = await self._receive()
            self.emit("signal", obj)

    async def stop(self):
        """Stop the signaling loop."""
        self._end_signaling_loop.set()
