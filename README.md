# peerjs-python

Python port of [PeerJS](https://github.com/peers) client. Tracked in issue [#160](https://github.com/peers/peerjs/issues/610) of the official PeerJS project.

Enables [Progressive Web Apps](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps) to discover and pair directly with Python apps using secure, browser supported [WebRTC](https://webrtc.org/) protocol. 

Uses [aiortc](https://github.com/aiortc/aiortc) as Python WebRTC provider.

![WebRTC logo](https://webrtc.org/assets/images/webrtc-logo-horiz-retro-300x60.png)

## Motivation

This project was originally motivated while searching for a way to: 
-  Connect a Progressive Web App ([Ambianic UI](https://github.com/ambianic/ambianic-ui)) directly and securely to an edge device ([Ambianic Edge](https://github.com/ambianic/ambianic-edge)) running Python app on a Raspberry Pi behind a home Internet router. 

Other key goals:
-  Easy Airdrop-like plug and play discovery and pairing between web app and edge devices. 
-  Rely only on standard broadly supported web browser features for the web app.
-  No proprietary browser plug-ins. 
-  No intermediary cloud service providers to store and sync user data. 
-  No tedious and brittle setup of dynamic DNS host per edge device with SSH tunnel between a public host name and the edge device.
-  No need to obtain and manage web host SSL certificates signed by a public CA for each edge device.

## Project Status

Initial working prototype completed. PeerJS Python is now able to connect over WebRTC DataChannel to PeerJS in the browser and exchange messages.

-  [x] Complete and test connectivity with signaling server (peerjs-server).
-  [x] Complete and test connectivity with web app peers.
-  [ ] >90% code coverage with CI tests.
-  [ ] Release to PyPi.
  
