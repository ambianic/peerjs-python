"""Manage discovery of other peers in the same local room.

Same room defined as shared WiFi/LAN and Public IP Address.
"""

from .peer import Peer
import logging
from .api import API

log = logging.getLogger(__name__)


class PeerRoom:
    """Peer's local room construct."""

    def __init__(self, peer: Peer):
        """Create PeerRoom instance for a given peer."""
        # the peer this room is associated with
        self._peer = peer
        self._roomId: str = None
        self._api = API(self._peer.options)

    async def _restCall(self, http_method=None, rest_method=None):
        log.debug('REST Call {} {}', http_method, rest_method)
        url = self._api._buildUrl(method=rest_method)
        try:
            response = await self._api._fetch(url=url, method=http_method)
            if response.status != 200:
                raise ConnectionError()
            return response.json()
        except Exception as error:
            msg = f"REST Error for {http_method} {url}."
            f" HTTP Response Status:{response.status}"
            log.error(msg, error)
            raise ConnectionError(msg, error)

    async def _getRoomId(self):
        """Get this peer's current local Room ID from the signaling server."""
        rest_method = 'room/id'
        result = await self._restCall(rest_method=rest_method)
        if result:
            self._roomId = result.roomId
        log.debug('this roomId is {}', self._roomId)
        return self._roomId

    async def _joinRoom(self):
        """Make this peer visible to other peers in the same room."""
        path = f'room/${self._roomId}/join'
        method = 'POST'
        members = await self._restCall(http_method=method, rest_method=path)
        log.debug('Joined room %s, Members: %s', self._roomId, members)
        return members

    async def getRoomMembers(self, roomId):
        """Get the list of peers in a room."""
        if not self._roomId:
            members = await self.join()
        else:
            path = f'room/{self._roomId}/members'
            members = await self._restCall(path=path)
        log.debug('Room {}, members {}', self._roomId, members)
        return members

    async def join(self):
        """Get this peer's local room ID and join that room."""
        if not self._roomId:
            self._roomId = await self._getRoomId()
        members = await self._joinRoom()
        return members
