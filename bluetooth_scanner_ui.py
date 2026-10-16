#!/usr/bin/env python3
"""A native macOS window for scanning nearby Bluetooth Low Energy devices."""

from __future__ import annotations

from datetime import datetime

import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSButton,
    NSFont,
    NSMakeRect,
    NSScrollView,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from CoreBluetooth import CBCentralManager, CBCentralManagerStatePoweredOn
from Foundation import NSObject, NSURL
from WebKit import WKWebView, WKWebViewConfiguration

SCAN_TIMEOUT = 10  # seconds


class ScannerWindow(NSObject):
    """Owns the window and receives CoreBluetooth discovery callbacks."""

    def init(self):
        self = objc.super(ScannerWindow, self).init()
        if self is None:
            return None
        self.devices: dict[str, tuple[str, int, str]] = {}
        self.peripherals: dict[str, any] = {}  # Store actual peripheral objects
        self.scanning = False
        self.favorites: set[str] = set()
        self.connected_device: str | None = None
        self.connection_pending: str | None = None
        self._build_window()
        self.manager = CBCentralManager.alloc().initWithDelegate_queue_options_(self, None, None)
        return self

    @objc.python_method
    def _build_window(self):
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
        )
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 760, 500), style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("Bluetooth LE Scanner")
        self.window.center()
        content = self.window.contentView()

        self.status = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 452, 500, 25))
        self.status.setBezeled_(False)
        self.status.setDrawsBackground_(False)
        self.status.setEditable_(False)
        self.status.setStringValue_("Preparing Bluetooth…")
        content.addSubview_(self.status)

        self.start_button = self._button("Start Scan", "startScan:", 535)
        self.stop_button = self._button("Stop", "stopScan:", 630)
        self.stop_button.setEnabled_(False)
        self.clear_button = self._button("Clear", "clearResults:", 690)
        self.export_button = self._button("Export", "exportDevices:", 480)
        for button in (self.start_button, self.stop_button, self.clear_button, self.export_button):
            content.addSubview_(button)

        # Create webview for signal visualization
        config = WKWebViewConfiguration.alloc().init()
        self.results = WKWebView.alloc().initWithFrame_configuration_(
            NSMakeRect(20, 20, 720, 415), config
        )
        self.results.setAutoresizingMask_(18)  # NSViewWidthSizable | NSViewHeightSizable
        # Add script message handler for device actions
        self.results.configuration().userContentController().addScriptMessageHandler_name_(self, "deviceAction")
        content.addSubview_(self.results)

    @objc.python_method
    def _button(self, title, action, x):
        button = NSButton.alloc().initWithFrame_(NSMakeRect(x, 448, 75, 30))
        button.setTitle_(title)
        button.setBezelStyle_(NSBezelStyleRounded)
        button.setTarget_(self)
        button.setAction_(action)
        return button

    def centralManagerDidUpdateState_(self, central):
        if central.state() == CBCentralManagerStatePoweredOn:
            self.status.setStringValue_("Bluetooth is ready. Click Start Scan.")
            self.start_button.setEnabled_(True)
            return
        states = {1: "resetting", 2: "unsupported", 3: "not authorized", 4: "powered off"}
        self.status.setStringValue_(f"Bluetooth is {states.get(central.state(), 'unavailable')}.")
        self.start_button.setEnabled_(False)
        self.stop_button.setEnabled_(False)

    def startScan_(self, _sender):
        if self.manager.state() != CBCentralManagerStatePoweredOn:
            self.status.setStringValue_("Bluetooth is not ready yet.")
            return
        self.manager.scanForPeripheralsWithServices_options_(None, None)
        self.scanning = True
        self.status.setStringValue_(f"Scanning for nearby Bluetooth LE devices… (auto-stop in {SCAN_TIMEOUT}s)")
        self.start_button.setEnabled_(False)
        self.stop_button.setEnabled_(True)
        # Schedule automatic stop after timeout
        self.performSelector_withObject_afterDelay_("autoStopScan:", None, SCAN_TIMEOUT)

    def stopScan_(self, _sender):
        if not self.scanning:
            return
        self.scanning = False
        self.manager.stopScan()
        self.status.setStringValue_(f"Scan stopped — {len(self.devices)} device(s) found.")
        self.start_button.setEnabled_(self.manager.state() == CBCentralManagerStatePoweredOn)
        self.stop_button.setEnabled_(False)

    def autoStopScan_(self, _sender):
        """Automatic scan stop after timeout."""
        if not self.scanning:
            return
        self.scanning = False
        self.manager.stopScan()
        self.status.setStringValue_(f"Scan stopped (timeout) — {len(self.devices)} device(s) found.")
        self.start_button.setEnabled_(self.manager.state() == CBCentralManagerStatePoweredOn)
        self.stop_button.setEnabled_(False)

    def centralManager_didConnectPeripheral_(self, central, peripheral):
        """Called when a peripheral is successfully connected."""
        identifier = str(peripheral.identifier())
        self.connected_device = identifier
        self.connection_pending = None
        
        if identifier in self.devices:
            device_name = self.devices[identifier][0]
            self.status.setStringValue_(f"✓ Connected to {device_name}")
        
        self._render_results()
        print(f"Connected to peripheral: {identifier}")

    def centralManager_didFailToConnectPeripheral_error_(self, central, peripheral, error):
        """Called when connection attempt fails."""
        identifier = str(peripheral.identifier())
        self.connection_pending = None
        
        if identifier in self.devices:
            device_name = self.devices[identifier][0]
            error_msg = error.localizedDescription() if error else "Unknown error"
            self.status.setStringValue_(f"✗ Failed to connect to {device_name}: {error_msg}")
        
        self._render_results()
        print(f"Failed to connect to {identifier}: {error}")

    def centralManager_didDisconnectPeripheral_error_(self, central, peripheral, error):
        """Called when a peripheral disconnects."""
        identifier = str(peripheral.identifier())
        
        if self.connected_device == identifier:
            self.connected_device = None
        
        if identifier in self.devices:
            device_name = self.devices[identifier][0]
            self.status.setStringValue_(f"Disconnected from {device_name}")
        
        self._render_results()
        print(f"Disconnected from {identifier}")

    def clearResults_(self, _sender):
        self.devices.clear()
        self._render_results()
        self.status.setStringValue_("Results cleared.")

    def exportDevices_(self, _sender):
        """Export discovered devices to CSV file."""
        if not self.devices:
            self.status.setStringValue_("No devices to export.")
            return
        
        import csv
        from pathlib import Path
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"bluetooth_devices_{timestamp}.csv"
        filepath = Path.home() / "Desktop" / filename
        
        try:
            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Device Name", "RSSI (dBm)", "Signal %", "Last Seen", "Identifier", "Favorite"])
                
                for identifier, (name, rssi, last_seen) in sorted(
                    self.devices.items(), key=lambda item: item[1][1], reverse=True
                ):
                    signal_strength = self._get_signal_strength(rssi)
                    is_favorite = "⭐" if identifier in self.favorites else ""
                    writer.writerow([name, rssi, signal_strength, last_seen, identifier, is_favorite])
            
            self.status.setStringValue_(f"Exported {len(self.devices)} device(s) to {filepath}")
        except Exception as e:
            self.status.setStringValue_(f"Export failed: {e}")

    def userContentController_didReceiveScriptMessage_(self, controller, message):
        """Handle JavaScript messages from web view."""
        import json
        
        try:
            data = json.loads(message.body())
            action = data.get("action")
            device_id = data.get("device_id")
            
            if action == "toggle_favorite" and device_id:
                if device_id in self.favorites:
                    self.favorites.remove(device_id)
                else:
                    self.favorites.add(device_id)
                self._render_results()
                
            elif action == "copy_id" and device_id:
                self._copy_to_clipboard(device_id)
                
            elif action == "connect" and device_id and device_id in self.devices:
                if self.connected_device == device_id:
                    # Disconnect
                    if device_id in self.peripherals:
                        self.manager.cancelPeripheralConnection_(self.peripherals[device_id])
                    self.connected_device = None
                    self.connection_pending = None
                    self.status.setStringValue_(f"Disconnected from {self.devices[device_id][0]}")
                else:
                    # Connect
                    if device_id in self.peripherals:
                        peripheral = self.peripherals[device_id]
                        self.connection_pending = device_id
                        self.status.setStringValue_(f"Connecting to {self.devices[device_id][0]}…")
                        self.manager.connectPeripheral_options_(peripheral, None)
                    else:
                        self.status.setStringValue_("Device not found. Rescan to refresh.")
                
                self._render_results()
        except Exception as e:
            print(f"Error handling message: {e}")
            self.status.setStringValue_(f"Error: {str(e)}")

    @objc.python_method
    def _copy_to_clipboard(self, text: str):
        """Copy text to macOS clipboard."""
        from AppKit import NSPasteboard, NSPasteboardTypeString
        
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(text, NSPasteboardTypeString)
        self.status.setStringValue_(f"Copied to clipboard ✓")

    def centralManager_didDiscoverPeripheral_advertisementData_RSSI_(
        self, _central, peripheral, advertisement_data, rssi
    ):
        identifier = str(peripheral.identifier())
        name = peripheral.name() or advertisement_data.get("kCBAdvDataLocalName") or "(unnamed)"
        self.devices[identifier] = (str(name), int(rssi), datetime.now().strftime("%H:%M:%S"))
        self.peripherals[identifier] = peripheral  # Store the actual peripheral object
        self._render_results()
        self.status.setStringValue_(f"Scanning — {len(self.devices)} device(s) found.")

    @objc.python_method
    def _get_signal_color(self, rssi: int) -> str:
        """Return color based on RSSI signal strength."""
        if rssi >= -50:
            return "#10b981"  # green - excellent
        elif rssi >= -70:
            return "#3b82f6"  # blue - good
        elif rssi >= -80:
            return "#f59e0b"  # amber - fair
        else:
            return "#ef4444"  # red - poor

    @objc.python_method
    def _get_signal_strength(self, rssi: int) -> int:
        """Convert RSSI to 0-100 percentage."""
        # RSSI ranges from about -100 (weakest) to -30 (strongest)
        percentage = max(0, min(100, (rssi + 100) * 2))
        return int(percentage)

    @objc.python_method
    def _render_results(self):
        """Render device list as HTML with signal strength visualization and interactive features."""
        html_parts = [
            '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #f9fafb;
            margin: 0;
            padding: 16px;
            color: #1f2937;
        }
        .device-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .device-card {
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 12px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            transition: all 0.2s ease;
        }
        .device-card.connected {
            border-color: #10b981;
            background: #f0fdf4;
        }
        .device-card.favorite {
            border-left: 4px solid #fbbf24;
        }
        .device-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        .device-name {
            font-weight: 600;
            font-size: 14px;
            max-width: 250px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .device-badges {
            display: flex;
            gap: 6px;
            align-items: center;
        }
        .badge {
            font-size: 11px;
            padding: 2px 6px;
            border-radius: 4px;
            background: #e5e7eb;
            color: #374151;
        }
        .badge.connected {
            background: #d1fae5;
            color: #059669;
        }
        .badge.favorite {
            background: #fef3c7;
            color: #d97706;
        }
        .device-info {
            display: flex;
            gap: 16px;
            font-size: 12px;
            color: #6b7280;
            margin-top: 4px;
        }
        .device-id {
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 11px;
            color: #9ca3af;
            margin-top: 6px;
            word-break: break-all;
        }
        .signal-container {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 8px;
        }
        .signal-bar {
            flex: 1;
            height: 6px;
            background-color: #e5e7eb;
            border-radius: 3px;
            overflow: hidden;
        }
        .signal-fill {
            height: 100%;
            border-radius: 3px;
            transition: width 0.3s ease;
        }
        .signal-rssi {
            font-size: 12px;
            font-weight: 600;
            min-width: 45px;
            text-align: right;
        }
        .device-actions {
            display: flex;
            gap: 6px;
            margin-top: 8px;
        }
        .action-btn {
            padding: 4px 8px;
            font-size: 11px;
            border: 1px solid #d1d5db;
            background: #f9fafb;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .action-btn:hover {
            background: #f3f4f6;
            border-color: #9ca3af;
        }
        .action-btn.connect {
            background: #3b82f6;
            color: white;
            border-color: #3b82f6;
        }
        .action-btn.connect:hover {
            background: #2563eb;
        }
        .action-btn.connect.connected {
            background: #10b981;
            border-color: #10b981;
        }
        .action-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
    </style>
</head>
<body>
    <div class="device-list">
<script>
function sendAction(action, deviceId) {
    webkit.messageHandlers.deviceAction.postMessage(JSON.stringify({
        action: action,
        device_id: deviceId
    }));
}
</script>
'''
        ]

        if not self.devices:
            html_parts.append(
                '<div style="text-align: center; color: #9ca3af; padding: 20px;">'
                'No devices found. Start scanning to see results.</div>'
            )
        else:
            # Sort by RSSI (strongest first)
            for identifier, (name, rssi, last_seen) in sorted(
                self.devices.items(), key=lambda item: item[1][1], reverse=True
            ):
                signal_color = self._get_signal_color(rssi)
                signal_strength = self._get_signal_strength(rssi)
                is_favorite = identifier in self.favorites
                is_connected = identifier == self.connected_device
                is_connecting = identifier == self.connection_pending
                
                card_classes = "device-card"
                if is_connected:
                    card_classes += " connected"
                if is_favorite:
                    card_classes += " favorite"
                
                favorite_btn = "⭐" if is_favorite else "☆"
                connect_btn_class = "action-btn connect"
                if is_connected:
                    connect_btn_class += " connected"
                
                if is_connecting:
                    connect_btn_text = "Connecting…"
                elif is_connected:
                    connect_btn_text = "Disconnect"
                else:
                    connect_btn_text = "Connect"
                
                html_parts.append(f'''        <div class="{card_classes}">
            <div class="device-header">
                <div class="device-name">{name}</div>
                <div class="device-badges">
                    <div class="signal-rssi" style="color: {signal_color};">{rssi} dBm</div>
                </div>
            </div>
            <div class="device-info">
                <span>📡 Last seen: {last_seen}</span>
''')
                
                if is_connecting:
                    html_parts.append('                <span class="badge" style="background: #fbbf24; color: #92400e;">⏳ Connecting…</span>')
                elif is_connected:
                    html_parts.append('                <span class="badge connected">✓ Connected</span>')
                if is_favorite:
                    html_parts.append('                <span class="badge favorite">⭐ Favorite</span>')
                
                html_parts.append(f'''            </div>
            <div class="signal-container">
                <div class="signal-bar">
                    <div class="signal-fill" style="width: {signal_strength}%; background-color: {signal_color};"></div>
                </div>
                <span style="font-size: 12px; color: #6b7280; min-width: 30px;">{signal_strength}%</span>
            </div>
            <div class="device-id">🆔 {identifier}</div>
            <div class="device-actions">
                <button class="action-btn" onclick="sendAction('toggle_favorite', '{identifier}')">
                    {favorite_btn} Favorite
                </button>
                <button class="action-btn" onclick="sendAction('copy_id', '{identifier}')">
                    📋 Copy ID
                </button>
                <button class="{connect_btn_class}" onclick="sendAction('connect', '{identifier}')" {'' if not is_connecting else 'disabled'}>
                    {'⏳' if is_connecting else '🔗'} {connect_btn_text}
                </button>
            </div>
        </div>
''')

        html_parts.append(
            '''    </div>
</body>
</html>
'''
        )

        html_content = "".join(html_parts)
        self.results.loadHTMLString_baseURL_(html_content, NSURL.fileURLWithPath_("/"))


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    controller = ScannerWindow.alloc().init()
    controller.window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)
    app.run()


if __name__ == "__main__":
    main()
