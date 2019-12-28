"""Helper utility structures and methods."""
from .supports import Supports
from aiortc import RTCDataChannel, RTCPeerConnection
import math
import asyncio
import aiofiles

DEFAULT_CONFIG = {
  'iceServers': [
    {'urls': "stun:stun.l.google.com:19302"},
    {'urls': "turn:0.peerjs.com:3478",
     'username': "peerjs",
     'credential': "peerjsp"}
  ],
  'sdpSemantics': "unified-plan"
}


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
        self.browser = Supports.getBrowser()
        self.browserVersion = Supports.getVersion()
        # Lists which features are supported
        self.supports = self._supported()
        # Binary stuff
        self._dataCount: int = 1

    def validateId(self, id: str) -> bool:
        """Ensure alphanumeric ids."""
        # Allow empty ids
        return not id or id.isalnum()

    def _supported(self):
        supported = {
            'browser': Supports.isBrowserSupported(),
            'webRTC': Supports.isWebRTCSupported(),
            'audioVideo': False,
            'data': False,
            'binaryBlob': False,
            'reliable': False,
        }
        if not supported.webRTC:
            return supported
        pc: RTCPeerConnection
        try:
            pc = RTCPeerConnection(DEFAULT_CONFIG)
            supported.audioVideo = True
            dc: RTCDataChannel
            try:
                dc = pc.createDataChannel("_PEERJSTEST", {'ordered': True})
                supported.data = True
                supported.reliable = True if dc.ordered else False
                # Test for Binary mode support
                try:
                    dc.binaryType = "blob"
                    supported.binaryBlob = not Supports.isIOS
                except Exception:
                    pass
            finally:
                if dc:
                    dc.close()
        finally:
            if pc:
                pc.close()
        return supported

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

    async def blobToArrayBuffer(self, blob=None, callback=None) -> None:
        """Load a blog into an array buffer."""
        # callback type hint: (arg: ArrayBuffer) -> None
        async def load_file():
            async with aiofiles.open(blob, mode='r') as f:
                contents = await f.read()
                callback(contents)
        asyncio.create_task(load_file)

    def binaryStringToArrayBuffer(binary: str = None) -> bytes:
        """Convert a string to an immutable byte array."""
        byteArray = binary.encode()
        return byteArray

    def randomToken() -> str:
        """Generate a random token."""
        return math.random() \
            .toString(36) \
            .substr(2)

    def isSecure(url=None) -> bool:
        """Return True if using https for the signaling server connection."""
        return url.startswith("https:")


# initialize a global util instance to be used by other modules
util = Util()
