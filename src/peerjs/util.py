"""Helper utility structures and methods."""
import logging
import math
import re
from dataclasses import dataclass
from uuid import uuid4
# import msgpack

from aiortc.rtcconfiguration import RTCConfiguration, RTCIceServer

# import asyncio
# import aiofiles

log = logging.getLogger(__name__)

DEFAULT_CONFIG = RTCConfiguration(
    iceServers=[
        RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
        RTCIceServer(urls=["turn:0.peerjs.com:3478"],
                     username="peerjs",
                     credential="peerjsp"
                     )
        ]
    )


@dataclass
class UtilSupports:
    """WebRTC parameters supported by this library."""

    webRTC: bool = True
    browser: str = 'aiortc'
    audioVideo: bool = True
    data: bool = True
    binaryBlob: bool = False
    reliable: bool = True


class Util:
    """Various helper methods."""

    def noop(self) -> None:
        """No op."""
        pass

    def __init__(self):
        """Create utility constructs."""
        self.CLOUD_HOST = "0.peerjs.com"
        self.CLOUD_PORT = 443
        # Browsers that need chunking:
        self.chunkedBrowsers = {'Chrome': 1, 'chrome': 1}
        # The original 60000 bytes setting does not work when
        # sending data from Firefox to Chrome,
        # which is "cut off" after 16384 bytes and delivered individually.
        self.chunkedMTU = 16300
        # browser-agnostic default config
        self.defaultConfig = DEFAULT_CONFIG
        self.browser = "peerjs-python"  # Supports.getBrowser()
        self.browserVersion = "0.1"  # Supports.getVersion()
        # Lists which features are supported
        # Binary stuff
        self._dataCount: int = 1
        self._supports = UtilSupports()
        # self.pack = msgpack.packb
        # self.unpack = msgpack.unpackb

    def validateId(self, id: str = None) -> bool:
        """Ensure alphanumeric ids."""
        # Allow empty ids
        valid = not id or re.match('^[A-Za-z0-9]+(?:[ _-][A-Za-z0-9]+)*$', id)
        log.debug('ID %s is %s valid', id, "" if valid else "not")
        return valid

    @property
    def supports(self):
        """Return dict of supported WebRTC features."""
        return self._supports

    def chunk(self, blob):
        """Break up a blob into a list of smaller chunks for the wire."""
        # return type hint:
        #   { __peerData: number, n: number, total: number, data: Blob }[]
        chunks = []
        size = blob.size
        total = math.ceil(size / util.chunkedMTU)

        index = 0
        start = 0

        while (start < size):
            end = math.min(size, start + util.chunkedMTU)
            b = blob.slice(start, end)
            chunk = {
                '__peerData': self._dataCount,
                'n': index,
                'data': b,
                'total': total
                }
            chunks.push(chunk)
            start = end
            index += 1
        self._dataCount += 1
        return chunks

    # async def blobToArrayBuffer(self, blob=None, callback=None) -> None:
    #     """Load a blog into an array buffer."""
    #     # callback type hint: (arg: ArrayBuffer) -> None
    #     async def load_file():
    #         async with aiofiles.open(blob, mode='r') as f:
    #             contents = await f.read()
    #             callback(contents)
    #     asyncio.create_task(load_file)

    def binaryStringToArrayBuffer(self, binary: str = None) -> bytes:
        """Convert a string to an immutable byte array."""
        byteArray = binary.encode()
        return byteArray

    def randomToken(self) -> str:
        """Generate a random token."""
        token = str(uuid4())
        log.debug('Generated random token: %s', token)
        return token

    def isSecure(self, url=None) -> bool:
        """Return True if using https for the signaling server connection."""
        return url.startswith("https:")


# initialize a global util instance to be used by other modules
util = Util()
