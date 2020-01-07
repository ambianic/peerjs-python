"""Client side abstraction for commonly used REST APIs."""

import logging
import random
import time
from typing import Any

import aiohttp

from .enums import HttpMethod
from .util import util

log = logging.getLogger(__name__)


class API:
    """Client side methods for commonly used REST APIs."""

    def __init__(self, options: Any = None):
        """Create API instance."""
        self._options = options
        log.debug('API options: %s', options)

    def _buildUrl(self, method: str = None) -> str:
        log.debug('port %s', self._options.port)
        protocol = "https://" if self._options.secure else "http://"
        url = f'{protocol}{self._options.host}:' \
            f'{self._options.port}{self._options.path}{self._options.key}' \
            f'/method'
        queryString = f'?ts={time.monotonic()}{random.random()}'
        url += queryString
        log.debug('built url: %s', url)
        return url

    @staticmethod
    async def fetch(url=None, method=None, body=None):
        """Similar to web browser JavaScript fetch."""
        if not method:
            method = HttpMethod.GET
        async with aiohttp.ClientSession() as session:
            if method == HttpMethod.GET:
                async with session.get(url) as response:
                    return response
            elif method == HttpMethod.POST:
                async with session.post(url, data=body) as response:
                    return await response
            else:
                raise NotImplementedError(
                    f"HTTP requst method {method} not implemented yet. "
                    "Contributions welcome!")

    async def retrieveId(self):
        """Get a unique ID from the server and initialize with it."""
        url = self._buildUrl("id")
        try:
            response = await API.fetch(url)
            if response.status != 200:
                raise ConnectionError(f'Error. Status:{response.status}')
            return response.text()
        except Exception as error:
            log.error("Error retrieving ID: %s", error)
            pathError = ""
            if self._options.path == "/" and \
               self._options.host != util.CLOUD_HOST:
                pathError = \
                    " If you passed in a 'path' to your "
                " self-hosted PeerServer, "
                " you'll also need to pass in that "
                " same path when creating a new "
                " Peer."
                raise ConnectionError(
                    "Could not get an ID from the server." +
                    pathError)
