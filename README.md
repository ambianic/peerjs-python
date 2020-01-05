# peerjs-python

Python port of [PeerJS](https://github.com/peers) client.

Enables Python apps to discover and pair with remote web apps running [PeerJS](https://github.com/peers/peerjs). Uses [aiortc](https://github.com/aiortc/aiortc) as Python WebRTC provider.

## Motivation

This project was originally motivated while searching for a way to: 
-  Connect a Progressive Web App (Ambianic UI) directly and securely to an edge device (Ambianic Edge) running Python app on a Raspberry Pi behind a home Internet router. 

Other key goals:
-  Easy Airdrop-like plug and play discovery and pairing between web app and edge device. 
-  Rely only on standard broadly supported web browser features for the web app.
-  No proprietary browser plug-ins. 
-  No intermediary trusted cloud service to store and sync user data. 
-  No tedious and brittle setup of dynamic DNS host per edge device with SSH tunnel between a public host name and the edge device.
-  No need to obtain and manage SSL certificate signed by a public CA for each edge device.

## Project Status

Early development stage. The initial focus is on p2p datachannel support. Contributions are welcome.
