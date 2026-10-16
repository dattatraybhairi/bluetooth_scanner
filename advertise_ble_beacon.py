#!/usr/bin/env python3
"""Advertise a harmless custom BLE beacon from a Mac using CoreBluetooth.

macOS sends the advertisement repeatedly while this program is running. Apple
does not expose a public API for sending arbitrary raw advertisement packets,
so this uses the supported local-name and service-UUID fields instead.
"""

from __future__ import annotations

import argparse
import signal

import objc
from CoreBluetooth import (
    CBAdvertisementDataLocalNameKey,
    CBAdvertisementDataServiceUUIDsKey,
    CBPeripheralManager,
    CBPeripheralManagerStatePoweredOn,
    CBUUID,
)
from Foundation import NSObject, NSRunLoop, NSDate


class BeaconAdvertiser(NSObject):
    def initWithName_serviceUUID_(self, name: str, service_uuid: str):
        self = objc.super(BeaconAdvertiser, self).init()
        if self is None:
            return None
        self.name = name
        self.service_uuid = service_uuid
        self.manager = CBPeripheralManager.alloc().initWithDelegate_queue_options_(self, None, None)
        return self

    def peripheralManagerDidUpdateState_(self, peripheral):
        if peripheral.state() != CBPeripheralManagerStatePoweredOn:
            states = {1: "resetting", 2: "unsupported", 3: "unauthorized", 4: "powered off"}
            print(f"Bluetooth peripheral mode is {states.get(peripheral.state(), 'unavailable')}.")
            return

        advertisement = {
            CBAdvertisementDataLocalNameKey: self.name,
            CBAdvertisementDataServiceUUIDsKey: [CBUUID.UUIDWithString_(self.service_uuid)],
        }
        peripheral.startAdvertising_(advertisement)
        print(f"Advertising '{self.name}' with service UUID {self.service_uuid}")
        print("macOS sends repeated BLE advertisements automatically. Press Ctrl-C to stop.")

    def peripheralManagerDidStartAdvertising_error_(self, _peripheral, error):
        if error is not None:
            print(f"Could not start advertising: {error}")

    def stop(self):
        self.manager.stopAdvertising()


def main() -> int:
    parser = argparse.ArgumentParser(description="Advertise a custom BLE beacon from macOS.")
    parser.add_argument("--name", default="StudyBeacon-01", help="BLE local name to broadcast")
    parser.add_argument(
        "--uuid",
        default="12345678-1234-1234-1234-1234567890AB",
        help="16-byte BLE service UUID to broadcast",
    )
    args = parser.parse_args()
    advertiser = BeaconAdvertiser.alloc().initWithName_serviceUUID_(args.name, args.uuid)

    def stop(_signum, _frame):
        advertiser.stop()
        print("\nAdvertising stopped.")
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    run_loop = NSRunLoop.currentRunLoop()
    while True:
        run_loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.5))


if __name__ == "__main__":
    raise SystemExit(main())
