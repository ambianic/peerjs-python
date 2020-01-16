# peerjs-python

Python port of [PeerJS](https://github.com/peers) client. Tracked in issue [#160](https://github.com/peers/peerjs/issues/610) of the official PeerJS project.

Enables [Progressive Web Apps](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps) to discover and pair directly with Python apps using secure, browser supported [WebRTC](https://webrtc.org/) protocol. 

Uses [aiortc](https://github.com/aiortc/aiortc) as Python WebRTC provider.

![WebRTC logo](https://webrtc.org/assets/images/webrtc-logo-horiz-retro-300x60.png)

## Motivation

This project was originally motivated while searching for a way to: 
-  Connect a Progressive Web App ([Ambianic UI](https://github.com/ambianic/ambianic-ui)) directly and securely to an edge device ([Ambianic Edge](https://github.com/ambianic/ambianic-edge)) running Python app on a Raspberry Pi behind a home Internet router. 

Other key requirements:
-  Easy Airdrop-like plug and play discovery and pairing between web app and edge devices. 
-  Direct peer-to-peer connectivity to minimize:
    - latency
    - architecture complexity
    - costs associated with traffic and hosting of tunneling servers
    - exposure to public server security attacks
-  Support for:
    - Secure connections
    - Bi-directional data-channel
    - Low latency audio/video media streaming
    - Bi-directional live audio/video media
-  Rely only on [standard](https://www.w3.org/TR/webrtc/) broadly supported web browser features.
    -  Stable mobile device support (iOS, Android, Raspberry Pi)
    -  Stable desktop OS support (Windows, Mac OS, Linux)
    -  No need for browser plug-ins
-  No intermediary cloud service providers to store and sync user data. 
-  No tedious and complicated NAT setups of dynamic DNS with SSH tunnels between public IP servers and edge devices behind firewall.
-  High throughput and scalability via lightweight signaling service without a persistence layer.

## Project Status

Initial working prototype completed. PeerJS Python is now able to connect over WebRTC DataChannel to PeerJS in the browser and exchange messages.

-  [x] Complete and test connectivity with signaling server (peerjs-server).
-  [x] Complete and test connectivity with web app peers.
-  [ ] >90% code coverage with CI tests.
-  [ ] Release to PyPi.
  
## Related Open Source projects

There are several great projects that solve the problem of accessing IoT devices behind firewall via tunneling servers.

- [Python Proxy](https://github.com/qwj/python-proxy): Asynchronous tunnel proxy implemented in Python 3 asyncio.
- [Proxy.py](https://github.com/abhinavsingh/proxy.py): HTTP proxy server written in Python. 
- [Inlets](https://github.com/inlets/inlets): Reverse proxy and service tunnel written in Go.
- [Macchina.io](https://github.com/my-devices/sdk): IoT tunneling proxy written in C++.
