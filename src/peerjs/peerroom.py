"""Manage discovery of other peers in the same local room.

Same room defined as shared WiFi/LAN and Public IP Address.
"""

import json
import logging

from .api import API
from .peer import Peer

log = logging.getLogger(__name__)


class PeerRoom:
    """Peer's local room construct."""

    def __init__(self, peer: Peer):
        """Create PeerRoom instance for a given peer."""
        # the peer this room is associated with
        self._peer = peer
        self._roomId: str = None
        self._api = API(self._peer.options)

    async def _restCall(self, http_method='GET', rest_method=None):
        log.debug('REST Call %s %s', http_method, rest_method)
        url = self._api._buildUrl(rest_method=rest_method)
        status, text = await API.fetch(url=url, method=http_method)
        if status != 200:
            raise ConnectionError(f'Unexpected status code {status} '
                                  f'for {url}')
        jsonified = json.loads(text)
        return jsonified

    @property
    def id(self):
        """UUID of this room."""
        return self._roomId

    async def _getRoomId(self):
        """Get this peer's current local Room ID from the signaling server."""
        log.debug('Retrieving room id for peer id: %s , token: %s',
                  self._peer.id,
                  self._peer.options.token)
        assert self._peer.id
        assert self._peer.options.token
        peer_auth = f'{self._peer.id}/{self._peer.options.token}'
        rest_method = f'{peer_auth}/room/id'
        result = await self._restCall(rest_method=rest_method)
        log.debug('result for %s is %s', rest_method, result)
        if result:
            self._roomId = result['roomId']
        log.debug('this roomId is %s', self._roomId)
        return self._roomId

    async def _joinRoom(self):
        """Make this peer visible to other peers in the same room."""
        log.debug('Joining room id for peer id: %s , token: %s',
                  self._peer.id,
                  self._peer.options.token)
        assert self._peer.id
        assert self._peer.options.token
        peer_auth = f'{self._peer.id}/{self._peer.options.token}'
        rest_method = f'{peer_auth}/room/{self._roomId}/join'
        method = 'POST'
        members = await self._restCall(http_method=method,
                                       rest_method=rest_method)
        log.debug('Joined room %s, Members: %s', self._roomId, members)
        return members

    async def getRoomMembers(self):
        """Get the list of peers in a room."""
        if not self._roomId:
            log.debug('Room id still unknown.')
            members = await self.join()
        else:
            path = f'room/{self._roomId}/members'
            members = await self._restCall(path=path)
        log.debug('Room %s, members %s', self._roomId, members)
        return members

    async def join(self):
        """Get this peer's local room ID and join that room."""
        if not self._roomId:
            self._roomId = await self._getRoomId()
        log.debug('Room id: %s', self._roomId)
        members = await self._joinRoom()
        return members
