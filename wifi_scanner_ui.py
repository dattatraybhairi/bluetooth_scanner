#!/usr/bin/env python3
"""A native macOS window for scanning nearby WiFi networks."""

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
    NSPasteboard,
    NSPasteboardTypeString,
)
from CoreWLAN import CWWiFiClient
from Foundation import NSObject, NSURL, NSNotificationCenter
from WebKit import WKWebView, WKWebViewConfiguration

SCAN_TIMEOUT = 10  # seconds


class WiFiScannerWindow(NSObject):
    """Owns the window and receives WiFi network scanning results."""

    def init(self):
        self = objc.super(WiFiScannerWindow, self).init()
        if self is None:
            return None
        self.networks: dict[str, tuple[str, int, str, str]] = {}  # SSID -> (SSID, RSSI, Security, Channel)
        self.scanning = False
        self.favorites: set[str] = set()
        self.connected_network: str | None = None
        self.connection_pending: str | None = None
        self._build_window()
        self.wifi_client = CWWiFiClient.sharedWiFiClient()
        self._get_current_network()
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
            NSMakeRect(0, 0, 800, 550), style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("WiFi Network Scanner")
        self.window.center()
        content = self.window.contentView()

        self.status = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 502, 550, 25))
        self.status.setBezeled_(False)
        self.status.setDrawsBackground_(False)
        self.status.setEditable_(False)
        self.status.setStringValue_("Preparing WiFi scan…")
        content.addSubview_(self.status)

        self.start_button = self._button("Start Scan", "startScan:", 575)
        self.stop_button = self._button("Stop", "stopScan:", 670)
        self.stop_button.setEnabled_(False)
        self.clear_button = self._button("Clear", "clearResults:", 730)
        self.export_button = self._button("Export", "exportNetworks:", 480)
        for button in (self.start_button, self.stop_button, self.clear_button, self.export_button):
            content.addSubview_(button)

        # Create webview for network visualization
        config = WKWebViewConfiguration.alloc().init()
        self.results = WKWebView.alloc().initWithFrame_configuration_(
            NSMakeRect(20, 20, 760, 470), config
        )
        self.results.setAutoresizingMask_(18)
        self.results.configuration().userContentController().addScriptMessageHandler_name_(self, "networkAction")
        content.addSubview_(self.results)

    @objc.python_method
    def _button(self, title, action, x):
        button = NSButton.alloc().initWithFrame_(NSMakeRect(x, 498, 75, 30))
        button.setTitle_(title)
        button.setBezelStyle_(NSBezelStyleRounded)
        button.setTarget_(self)
        button.setAction_(action)
        return button

    def startScan_(self, _sender):
        """Start scanning for WiFi networks."""
        self.status.setStringValue_(f"Scanning for WiFi networks… (auto-stop in {SCAN_TIMEOUT}s)")
        self.start_button.setEnabled_(False)
        self.stop_button.setEnabled_(True)
        self.scanning = True
        
        try:
            interface = self.wifi_client.interface()
            if interface is None:
                self.status.setStringValue_("WiFi not available.")
                self.start_button.setEnabled_(True)
                self.stop_button.setEnabled_(False)
                return
            
            # Perform scan
            networks, error = interface.scanForNetworksWithName_error_(None, None)
            
            if error:
                self.status.setStringValue_(f"Scan error: {error.localizedDescription()}")
            elif networks:
                self.networks.clear()
                for network in networks:
                    ssid = network.ssid() or "(Hidden Network)"
                    rssi = network.rssiValue()
                    security = self._get_security_string(network)
                    channel = f"Ch {network.wlanChannel().channelNumber()}" if network.wlanChannel() else "Unknown"
                    
                    self.networks[ssid] = (ssid, int(rssi), security, channel)
                
                self._render_results()
                self.status.setStringValue_(f"Found {len(self.networks)} network(s)")
            else:
                self.status.setStringValue_("No networks found.")
        except Exception as e:
            self.status.setStringValue_(f"Scan failed: {str(e)}")
        
        # Auto-stop after timeout
        self.performSelector_withObject_afterDelay_("autoStopScan:", None, SCAN_TIMEOUT)

    def stopScan_(self, _sender):
        if not self.scanning:
            return
        self.scanning = False
        self.status.setStringValue_(f"Scan stopped — {len(self.networks)} network(s) found.")
        self.start_button.setEnabled_(True)
        self.stop_button.setEnabled_(False)

    def autoStopScan_(self, _sender):
        """Automatic scan stop after timeout."""
        if not self.scanning:
            return
        self.scanning = False
        self.status.setStringValue_(f"Scan stopped (timeout) — {len(self.networks)} network(s) found.")
        self.start_button.setEnabled_(True)
        self.stop_button.setEnabled_(False)

    def clearResults_(self, _sender):
        self.networks.clear()
        self._render_results()
        self.status.setStringValue_("Results cleared.")

    def exportNetworks_(self, _sender):
        """Export discovered networks to CSV file."""
        if not self.networks:
            self.status.setStringValue_("No networks to export.")
            return
        
        import csv
        from pathlib import Path
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"wifi_networks_{timestamp}.csv"
        filepath = Path.home() / "Desktop" / filename
        
        try:
            with open(filepath, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["SSID", "RSSI (dBm)", "Signal %", "Security", "Channel", "Connected", "Favorite"])
                
                for ssid, (_, rssi, security, channel) in sorted(
                    self.networks.items(), key=lambda item: item[1][1], reverse=True
                ):
                    signal_strength = self._get_signal_strength(rssi)
                    is_connected = "✓" if ssid == self.connected_network else ""
                    is_favorite = "⭐" if ssid in self.favorites else ""
                    writer.writerow([ssid, rssi, signal_strength, security, channel, is_connected, is_favorite])
            
            self.status.setStringValue_(f"Exported {len(self.networks)} network(s) to {filepath}")
        except Exception as e:
            self.status.setStringValue_(f"Export failed: {e}")

    def userContentController_didReceiveScriptMessage_(self, controller, message):
        """Handle JavaScript messages from web view."""
        import json
        
        try:
            data = json.loads(message.body())
            action = data.get("action")
            network_ssid = data.get("network_ssid")
            
            if action == "toggle_favorite" and network_ssid:
                if network_ssid in self.favorites:
                    self.favorites.remove(network_ssid)
                else:
                    self.favorites.add(network_ssid)
                self._render_results()
                
            elif action == "copy_ssid" and network_ssid:
                self._copy_to_clipboard(network_ssid)
                
            elif action == "connect" and network_ssid and network_ssid in self.networks:
                if self.connected_network == network_ssid:
                    # Disconnect
                    self.connected_network = None
                    self.connection_pending = None
                    self.status.setStringValue_(f"Disconnected from {network_ssid}")
                else:
                    # Connect
                    self.connection_pending = network_ssid
                    self.status.setStringValue_(f"Connecting to {network_ssid}…")
                    # Note: Actual connection requires user interaction in macOS
                    self._attempt_connect(network_ssid)
                
                self._render_results()
        except Exception as e:
            print(f"Error handling message: {e}")
            self.status.setStringValue_(f"Error: {str(e)}")

    @objc.python_method
    def _attempt_connect(self, network_ssid: str):
        """Attempt to connect to WiFi network."""
        try:
            interface = self.wifi_client.interface()
            if interface is None:
                self.status.setStringValue_("WiFi interface not available.")
                return
            
            # In macOS, we need to get the network object first
            networks, _ = interface.scanForNetworksWithName_error_(network_ssid, None)
            
            if networks:
                network = networks[0]
                # Attempt connection (may show system password prompt)
                success, error = interface.associateToNetwork_password_error_(network, None, None)
                
                if success:
                    self.connected_network = network_ssid
                    self.connection_pending = None
                    self.status.setStringValue_(f"✓ Connected to {network_ssid}")
                else:
                    self.connection_pending = None
                    error_msg = error.localizedDescription() if error else "Unknown error"
                    self.status.setStringValue_(f"✗ Failed to connect: {error_msg}")
            else:
                self.connection_pending = None
                self.status.setStringValue_("Network not found in scan results.")
            
            self._render_results()
        except Exception as e:
            self.connection_pending = None
            self.status.setStringValue_(f"Connection error: {str(e)}")
            self._render_results()

    def _get_current_network(self):
        """Get currently connected WiFi network."""
        try:
            interface = self.wifi_client.interface()
            if interface:
                current_ssid = interface.ssid()
                if current_ssid:
                    self.connected_network = current_ssid
        except:
            pass

    @objc.python_method
    def _get_security_string(self, network) -> str:
        """Convert security type to readable string."""
        try:
            security_type = network.securityType()
            security_map = {
                0: "Open",
                1: "WEP",
                2: "WPA",
                3: "WPA2",
                4: "WPA3",
            }
            return security_map.get(security_type, "Unknown")
        except:
            return "Unknown"

    @objc.python_method
    def _get_signal_color(self, rssi: int) -> str:
        """Return color based on signal strength."""
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
        percentage = max(0, min(100, (rssi + 100) * 2))
        return int(percentage)

    @objc.python_method
    def _copy_to_clipboard(self, text: str):
        """Copy text to macOS clipboard."""
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        pasteboard.setString_forType_(text, NSPasteboardTypeString)
        self.status.setStringValue_("Copied to clipboard ✓")

    @objc.python_method
    def _render_results(self):
        """Render network list as HTML with signal strength visualization."""
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
        .network-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .network-card {
            background: white;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 12px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            transition: all 0.2s ease;
        }
        .network-card.connected {
            border-color: #10b981;
            background: #f0fdf4;
        }
        .network-card.favorite {
            border-left: 4px solid #fbbf24;
        }
        .network-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        .network-name {
            font-weight: 600;
            font-size: 14px;
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .network-badges {
            display: flex;
            gap: 6px;
            align-items: center;
            flex-wrap: wrap;
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
        .network-info {
            display: flex;
            gap: 16px;
            font-size: 12px;
            color: #6b7280;
            margin-top: 4px;
            flex-wrap: wrap;
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
        .network-actions {
            display: flex;
            gap: 6px;
            margin-top: 8px;
            flex-wrap: wrap;
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
    <div class="network-list">
<script>
function sendAction(action, networkSsid) {
    webkit.messageHandlers.networkAction.postMessage(JSON.stringify({
        action: action,
        network_ssid: networkSsid
    }));
}
</script>
'''
        ]

        if not self.networks:
            html_parts.append(
                '<div style="text-align: center; color: #9ca3af; padding: 20px;">'
                'No networks found. Start scanning to see results.</div>'
            )
        else:
            # Sort by RSSI (strongest first)
            for ssid, (_, rssi, security, channel) in sorted(
                self.networks.items(), key=lambda item: item[1][1], reverse=True
            ):
                signal_color = self._get_signal_color(rssi)
                signal_strength = self._get_signal_strength(rssi)
                is_favorite = ssid in self.favorites
                is_connected = ssid == self.connected_network
                is_connecting = ssid == self.connection_pending
                
                card_classes = "network-card"
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
            <div class="network-header">
                <div class="network-name">{ssid}</div>
                <div class="network-badges">
                    <div class="signal-rssi" style="color: {signal_color};">{rssi} dBm</div>
                </div>
            </div>
            <div class="network-info">
                <span>🔒 {security}</span>
                <span>📡 {channel}</span>
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
            <div class="network-actions">
                <button class="action-btn" onclick="sendAction('toggle_favorite', '{ssid}')">
                    {favorite_btn} Favorite
                </button>
                <button class="action-btn" onclick="sendAction('copy_ssid', '{ssid}')">
                    📋 Copy SSID
                </button>
                <button class="{connect_btn_class}" onclick="sendAction('connect', '{ssid}')" {'' if not is_connecting else 'disabled'}>
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
    controller = WiFiScannerWindow.alloc().init()
    controller.window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)
    app.run()


if __name__ == "__main__":
    main()
