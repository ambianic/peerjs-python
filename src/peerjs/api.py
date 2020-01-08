"""Client side abstraction for commonly used REST APIs."""

import logging
import random
import time
from typing import Any

import aiohttp

from .util import util

log = logging.getLogger(__name__)


class HttpMethod:
    """Http Request Method types."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


class API:
    """Client side methods for commonly used REST APIs."""

    def __init__(self, options: Any = None):
        """Create API instance."""
        self._options = options
        log.debug('API options: %s', options)

    def _buildUrl(self, rest_method: str = None) -> str:
        log.debug('port %s', self._options.port)
        protocol = "https://" if self._options.secure else "http://"
        url = f'{protocol}{self._options.host}:' \
            f'{self._options.port}{self._options.path}{self._options.key}' \
            f'/{rest_method}'
        queryString = f'?ts={time.monotonic()}{random.random()}'
        url += queryString
        log.debug('built url: %s', url)
        return url

    @staticmethod
    async def fetch(url=None, method='GET', body=None):
        """Similar to web browser JavaScript fetch."""
        log.debug('fetching \n method: [%s] \n url: %s \n body: %s',
                  method,
                  url,
                  body)
        if not method:
            method = HttpMethod.GET
        status: int = None
        text: str = None
        async with aiohttp.ClientSession() as session:
            if method == HttpMethod.GET:
                async with session.get(url) as response:
                    status = response.status
                    text = await response.text()
            elif method == HttpMethod.POST:
                async with session.post(url, data=body) as response:
                    log.debug('fetch POST response: %r', response)
                    status = response.status
                    text = await response.text()
            else:
                raise NotImplementedError(
                    f"HTTP requst method {method} not implemented yet. "
                    "Contributions welcome!")
            log.debug('fetch result status: %d, text: %s', status, text)
            return (status, text)

    async def retrieveId(self):
        """Get a unique ID from the server and initialize with it."""
        url = self._buildUrl(rest_method="id")
        try:
            status, text = await API.fetch(url)
            if status != 200:
                log.error("Unexpected status code retrieving ID: %r",
                          status)
                raise ConnectionError(f'Error. Status:{status}')
            log.debug("Retrieve ID response text: %r", text)
            return text
        except Exception as error:
            log.exception("Error retrieving ID: %r", error)
            pathError = ""
            if self._options.path == "/" and \
               self._options.host != util.CLOUD_HOST:
                pathError = \
                    " If you passed in a 'path' to your " \
                    " self-hosted PeerServer, " \
                    " you'll also need to pass in that " \
                    " same path when creating a new " \
                    " Peer."
                raise ConnectionError(
                    "Could not get an ID from the server." +
                    pathError)
