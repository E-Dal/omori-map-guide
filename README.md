# OMORI Map Guide

An interactive map atlas for OMORI — explore Faraway Town and Headspace, find watermelons, NPC rewards, and never get lost again.

## Goals

- Stitched outdoor world maps for FARAWAY TOWN and HEADSPACE
- Click-to-enter interiors (independent rooms shown side-by-side, not force-fit into the world map)
- Markers for collectibles (watermelons), NPC rewards, badge triggers
- Filterable by type / region / availability

## Status

Early WIP. Vanilla content only for now.

## Stack

- Static HTML site
- [Leaflet](https://leafletjs.com/) for the map viewer (zoom + pan + markers)
- Map tiles courtesy of [goats.dev](https://goats.dev/omori/) (vanilla maps)
- Hosted on GitHub Pages

## Data sources

- Game event data: extracted from decrypted vanilla `Map*.json` files
- Map images: [goats.dev](https://goats.dev/omori/) pre-rendered PNGs

## License

MIT for code. Game assets (map images, sprites) are property of OMOCAT.
