"""Client side abstraction for commonly used REST APIs."""

import time
import math
import logging
import aiohttp
from .enums import HttpMethod
from .util import util

log = logging.getLogger(__name__)


async def fetch(url=None, method=None, body=None):
    """Similar to web browser JavaScript fetch."""
    if not method:
        method = HttpMethod.GET
    async with aiohttp.ClientSession() as session:
        if method == HttpMethod.GET:
            async with session.get(url) as response:
                return await response
        elif method == HttpMethod.POST:
            async with session.post(url, data=body) as response:
                return await response
        else:
            raise NotImplementedError(
                f"HTTP requst method {method} not implemented yet. "
                "Contributions welcome!")


class API:
    """Client side methods for commonly used REST APIs."""

    def __init__(self, options=None):
        """Create API instance."""
        self._options = options

    def _buildUrl(self, method: str = None) -> str:
        protocol = "https://" if self._options.secure else "http://"
        url = \
            protocol + \
            self._options.host + \
            ":" + \
            self._options.port + \
            self._options.path + \
            self._options.key + \
            "/" + \
            method
        queryString = "?ts=" + time.monotonous() + "" + math.random()
        url += queryString
        return url

    async def retrieveId(self):
        """Get a unique ID from the server and initialize with it."""
        url = self._buildUrl("id")
        try:
            response = await fetch(url)
            if response.status != 200:
                raise ConnectionError(f'Error. Status:{response.status}')
            return response.text()
        except Exception as error:
            log.error("Error retrieving ID: {}", error)
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
