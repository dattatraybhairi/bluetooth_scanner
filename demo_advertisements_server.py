#!/usr/bin/env python3
"""Serve harmless, simulated BLE advertisement events for the iPhone demo app.

This does not use Bluetooth hardware or transmit any Bluetooth packets.
"""

from __future__ import annotations

import json
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


DEVICES = (
    {"id": "A1B2C3D4-0000-4000-8000-000000000001", "name": "Study Beacon One", "base_rssi": -48},
    {"id": "A1B2C3D4-0000-4000-8000-000000000002", "name": "Study Headphones", "base_rssi": -66},
    {"id": "A1B2C3D4-0000-4000-8000-000000000003", "name": "Study Tag", "base_rssi": -78},
)


class AdvertisementHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") != "/advertisement":
            self.send_error(404, "Use /advertisement")
            return
        device = random.choices(DEVICES, weights=(60, 28, 12), k=1)[0]
        event = {
            "id": device["id"],
            "name": device["name"],
            "rssi": device["base_rssi"] + random.randint(-8, 8),
        }
        body = json.dumps(event).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return  # Keep the Terminal output uncluttered.


def main():
    server = ThreadingHTTPServer(("0.0.0.0", 8765), AdvertisementHandler)
    print("Simulator running on port 8765.")
    print("On the iPhone, enter: http://YOUR_MAC_IP:8765/advertisement")
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSimulator stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
