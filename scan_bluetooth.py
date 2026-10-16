#!/usr/bin/env python3
"""Scan for nearby Bluetooth Low Energy devices on macOS.

macOS intentionally does not expose Bluetooth MAC addresses to applications.
The identifier printed by this program is a per-device UUID supplied by macOS.
"""

from __future__ import annotations

import argparse
import signal
import sys
from datetime import datetime

import objc
from CoreBluetooth import CBCentralManager, CBCentralManagerStatePoweredOn
from Foundation import NSObject, NSRunLoop, NSDate


class BluetoothScanner(NSObject):
    """CoreBluetooth delegate that prints newly discovered BLE peripherals."""

    def initWithShowDuplicates_(self, show_duplicates: bool):
        self = objc.super(BluetoothScanner, self).init()
        if self is None:
            return None
        self.show_duplicates = show_duplicates
        self.seen_identifiers: set[str] = set()
        self.manager = CBCentralManager.alloc().initWithDelegate_queue_options_(
            self, None, None
        )
        return self

    def centralManagerDidUpdateState_(self, central):
        if central.state() == CBCentralManagerStatePoweredOn:
            print("Bluetooth is on. Scanning for BLE devices… (Ctrl-C to stop)")
            options = {"CBCentralManagerScanOptionAllowDuplicatesKey": self.show_duplicates}
            central.scanForPeripheralsWithServices_options_(None, options)
        else:
            states = {
                0: "unknown",
                1: "resetting",
                2: "unsupported",
                3: "unauthorized",
                4: "powered off",
            }
            print(f"Bluetooth is not ready: {states.get(central.state(), 'unknown state')}")

    def centralManager_didDiscoverPeripheral_advertisementData_RSSI_(
        self, central, peripheral, advertisement_data, rssi
    ):
        identifier = str(peripheral.identifier())
        if not self.show_duplicates and identifier in self.seen_identifiers:
            return
        self.seen_identifiers.add(identifier)

        name = peripheral.name() or advertisement_data.get("kCBAdvDataLocalName") or "(unnamed)"
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {name} | id={identifier} | RSSI={int(rssi)} dBm")

    def stop(self):
        self.manager.stopScan()


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan nearby Bluetooth Low Energy devices.")
    parser.add_argument(
        "--duplicates",
        action="store_true",
        help="print repeated advertisements from the same device",
    )
    args = parser.parse_args()

    scanner = BluetoothScanner.alloc().initWithShowDuplicates_(args.duplicates)

    def stop_scan(_signum, _frame):
        print("\nStopping scan.")
        scanner.stop()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, stop_scan)
    signal.signal(signal.SIGTERM, stop_scan)

    # CoreBluetooth delivers delegate callbacks through the macOS run loop.
    run_loop = NSRunLoop.currentRunLoop()
    while True:
        run_loop.runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.5))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ModuleNotFoundError:
        print("Missing dependency. Run: python3 -m pip install -r requirements.txt", file=sys.stderr)
        raise SystemExit(1)
