#!/usr/bin/env python3
"""Combined Bluetooth & WiFi Scanner with dual-mode interface."""

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
    NSButtonTypeRadio,
    NSFont,
    NSMakeRect,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
    NSPasteboard,
    NSPasteboardTypeString,
)
from CoreBluetooth import CBCentralManager, CBCentralManagerStatePoweredOn
from CoreWLAN import CWWiFiClient
from Foundation import NSObject, NSURL
from WebKit import WKWebView, WKWebViewConfiguration

SCAN_TIMEOUT = 10  # seconds


class CombinedScannerWindow(NSObject):
    """Combined Bluetooth & WiFi Scanner."""

    def init(self):
        self = objc.super(CombinedScannerWindow, self).init()
        if self is None:
            return None
        
        self.mode = "bluetooth"  # or "wifi"
        self.scanning = False
        self.selected_device = None
        self.sort_mode = "rssi"  # rssi, name, connected
        self.filter_mode = "all"  # all, favorites, connected
        self.dark_mode = False
        self.auto_scan = False
        self.auto_scan_interval = 15
        
        # Bluetooth data
        self.bt_devices: dict[str, tuple[str, int, str]] = {}
        self.bt_peripherals: dict[str, any] = {}
        self.bt_favorites: set[str] = set()
        self.bt_connected: str | None = None
        
        # WiFi data
        self.wifi_networks: dict[str, tuple[str, int, str, str, str, str, str]] = {}
        self.wifi_objects: dict[str, any] = {}
        self.wifi_favorites: set[str] = set()
        self.wifi_connected: str | None = None
        
        self._build_window()
        
        # Initialize managers
        self.bt_manager = CBCentralManager.alloc().initWithDelegate_queue_options_(self, None, None)
        self.wifi_client = CWWiFiClient.sharedWiFiClient()
        self._get_current_wifi()
        
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
            NSMakeRect(0, 0, 1100, 700), style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("Network Scanner - Bluetooth & WiFi")
        self.window.center()
        content = self.window.contentView()

        # ===== TOP SECTION: Mode Selection =====
        y_pos = 655
        
        mode_label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, y_pos, 100, 25))
        mode_label.setStringValue_("Mode:")
        mode_label.setBezeled_(False)
        mode_label.setDrawsBackground_(False)
        mode_label.setEditable_(False)
        content.addSubview_(mode_label)
        
        # Bluetooth radio button
        self.bt_radio = NSButton.alloc().initWithFrame_(NSMakeRect(120, y_pos, 120, 25))
        self.bt_radio.setButtonType_(NSButtonTypeRadio)
        self.bt_radio.setTitle_("📱 Bluetooth")
        self.bt_radio.setState_(1)
        self.bt_radio.setTarget_(self)
        self.bt_radio.setAction_("switchMode:")
        self.bt_radio.setTag_(0)
        content.addSubview_(self.bt_radio)
        
        # WiFi radio button
        self.wifi_radio = NSButton.alloc().initWithFrame_(NSMakeRect(250, y_pos, 100, 25))
        self.wifi_radio.setButtonType_(NSButtonTypeRadio)
        self.wifi_radio.setTitle_("📡 WiFi")
        self.wifi_radio.setState_(0)
        self.wifi_radio.setTarget_(self)
        self.wifi_radio.setAction_("switchMode:")
        self.wifi_radio.setTag_(1)
        content.addSubview_(self.wifi_radio)

        # Status field
        self.status = NSTextField.alloc().initWithFrame_(NSMakeRect(400, y_pos, 290, 25))
        self.status.setBezeled_(False)
        self.status.setDrawsBackground_(False)
        self.status.setEditable_(False)
        self.status.setStringValue_("Ready")
        content.addSubview_(self.status)

        # Filter and sort controls
        self.auto_btn = self._button("Auto Off", "toggleAutoScan:", 580, y_pos)
        self.sort_btn = self._button("Sort: RSSI", "toggleSort:", 700, y_pos)
        self.filter_btn = self._button("Filter: All", "toggleFilter:", 820, y_pos)
        self.theme_btn = self._button("Dark Mode", "toggleTheme:", 940, y_pos)
        content.addSubview_(self.auto_btn)
        content.addSubview_(self.sort_btn)
        content.addSubview_(self.filter_btn)
        content.addSubview_(self.theme_btn)

        # ===== MIDDLE SECTION: List & Details =====
        # List view (full width)
        self.list_view = WKWebView.alloc().initWithFrame_configuration_(
            NSMakeRect(20, 140, 1060, 450), WKWebViewConfiguration.alloc().init()
        )
        self.list_view.configuration().userContentController().addScriptMessageHandler_name_(self, "deviceAction")
        content.addSubview_(self.list_view)

        # ===== BOTTOM SECTION: Control Buttons =====
        btn_y = 80
        
        self.start_btn = self._button("▶ Start", "startScan:", 20, btn_y)
        self.stop_btn = self._button("⏹ Stop", "stopScan:", 140, btn_y)
        self.stop_btn.setEnabled_(False)
        self.clear_btn = self._button("🗑 Clear", "clearResults:", 260, btn_y)

        for btn in [self.start_btn, self.stop_btn, self.clear_btn]:
            content.addSubview_(btn)

    @objc.python_method
    def _button(self, title, action, x, y):
        button = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, 80, 30))
        button.setTitle_(title)
        button.setBezelStyle_(NSBezelStyleRounded)
        button.setTarget_(self)
        button.setAction_(action)
        return button

    def toggleSort_(self, _sender):
        if self.sort_mode == "rssi":
            self.sort_mode = "name"
            self.sort_btn.setTitle_("Sort: Name")
        elif self.sort_mode == "name":
            self.sort_mode = "connected"
            self.sort_btn.setTitle_("Sort: Connected")
        else:
            self.sort_mode = "rssi"
            self.sort_btn.setTitle_("Sort: RSSI")
        self._update_list()

    def toggleFilter_(self, _sender):
        if self.filter_mode == "all":
            self.filter_mode = "favorites"
            self.filter_btn.setTitle_("Filter: Fav")
        elif self.filter_mode == "favorites":
            self.filter_mode = "connected"
            self.filter_btn.setTitle_("Filter: Connected")
        else:
            self.filter_mode = "all"
            self.filter_btn.setTitle_("Filter: All")
        self.selected_device = None
        self._update_list()

    def toggleTheme_(self, _sender):
        self.dark_mode = not self.dark_mode
        self.theme_btn.setTitle_("Light Mode" if self.dark_mode else "Dark Mode")
        self._update_list()

    def toggleAutoScan_(self, _sender):
        self.auto_scan = not self.auto_scan
        self.auto_btn.setTitle_("Auto On" if self.auto_scan else "Auto Off")
        self.status.setStringValue_("Auto scan enabled" if self.auto_scan else "Auto scan disabled")
        if self.auto_scan:
            self._schedule_auto_scan()

    def _schedule_auto_scan(self):
        if not self.auto_scan:
            return
        if not self.scanning:
            self.startScan_(None)
        self.performSelector_withObject_afterDelay_("_schedule_auto_scan", None, self.auto_scan_interval)

    def switchMode_(self, sender):
        """Switch between Bluetooth and WiFi modes."""
        if sender.tag() == 0:
            self.mode = "bluetooth"
        else:
            self.mode = "wifi"
        
        self.selected_device = None
        self._update_list()
        self.status.setStringValue_(f"Switched to {self.mode.upper()} mode")

    def startScan_(self, _sender):
        """Start scanning based on current mode."""
        self.status.setStringValue_(f"Scanning {self.mode}… (auto-stop in {SCAN_TIMEOUT}s)")
        self.start_btn.setEnabled_(False)
        self.stop_btn.setEnabled_(True)
        self.scanning = True
        
        if self.mode == "bluetooth":
            self._start_bt_scan()
        else:
            self._start_wifi_scan()
        
        self.performSelector_withObject_afterDelay_("autoStopScan:", None, SCAN_TIMEOUT)

    def stopScan_(self, _sender):
        if not self.scanning:
            return
        self.scanning = False
        
        if self.mode == "bluetooth":
            self.bt_manager.stopScan()
            count = len(self.bt_devices)
        else:
            count = len(self.wifi_networks)
        
        self.status.setStringValue_(f"Stopped — {count} items found")
        self.start_btn.setEnabled_(True)
        self.stop_btn.setEnabled_(False)

    def autoStopScan_(self, _sender):
        if not self.scanning:
            return
        self.scanning = False
        
        if self.mode == "bluetooth":
            self.bt_manager.stopScan()
            count = len(self.bt_devices)
        else:
            count = len(self.wifi_networks)
        
        self.status.setStringValue_(f"Scan timed out — {count} items found")
        self.start_btn.setEnabled_(True)
        self.stop_btn.setEnabled_(False)

    def clearResults_(self, _sender):
        if self.mode == "bluetooth":
            self.bt_devices.clear()
            self.bt_peripherals.clear()
        else:
            self.wifi_networks.clear()
        
        self.selected_device = None
        self._update_list()
        self.status.setStringValue_("Results cleared")

    def exportData_(self, _sender):
        """Export current mode data to CSV."""
        import csv
        from pathlib import Path
        
        if self.mode == "bluetooth":
            if not self.bt_devices:
                self.status.setStringValue_("No Bluetooth devices to export")
                return
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"bluetooth_devices_{timestamp}.csv"
            filepath = Path.home() / "Desktop" / filename
            
            try:
                with open(filepath, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["Device Name", "RSSI (dBm)", "Signal %", "Last Seen", "Identifier", "Favorite", "Connected"])
                    
                    for identifier, (name, rssi, last_seen) in sorted(
                        self.bt_devices.items(), key=lambda item: item[1][1], reverse=True
                    ):
                        signal_strength = self._get_signal_strength(rssi)
                        is_favorite = "⭐" if identifier in self.bt_favorites else ""
                        is_connected = "✓" if identifier == self.bt_connected else ""
                        writer.writerow([name, rssi, signal_strength, last_seen, identifier, is_favorite, is_connected])
                
                self.status.setStringValue_(f"Exported to {filepath}")
            except Exception as e:
                self.status.setStringValue_(f"Export failed: {e}")
        else:
            if not self.wifi_networks:
                self.status.setStringValue_("No WiFi networks to export")
                return
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"wifi_networks_{timestamp}.csv"
            filepath = Path.home() / "Desktop" / filename
            
            try:
                with open(filepath, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["SSID", "RSSI (dBm)", "Signal %", "Security", "Channel", "BSSID", "Band", "Width", "Favorite", "Connected"])
                    
                    for ssid, (_, rssi, security, channel, bssid, band, width) in sorted(
                        self.wifi_networks.items(), key=lambda item: item[1][1], reverse=True
                    ):
                        signal_strength = self._get_signal_strength(rssi)
                        is_favorite = "⭐" if ssid in self.wifi_favorites else ""
                        is_connected = "✓" if ssid == self.wifi_connected else ""
                        writer.writerow([ssid, rssi, signal_strength, security, channel, bssid, band, width, is_favorite, is_connected])
                
                self.status.setStringValue_(f"Exported to {filepath}")
            except Exception as e:
                self.status.setStringValue_(f"Export failed: {e}")

    def userContentController_didReceiveScriptMessage_(self, controller, message):
        """Handle clicks from list view."""
        import json
        
        try:
            data = json.loads(message.body())
            action = data.get("action")
            item_id = data.get("item_id")
            
            if action == "select" and item_id:
                self.selected_device = item_id
                self._update_list()
            elif action == "toggle_favorite" and item_id:
                if self.mode == "bluetooth":
                    if item_id in self.bt_favorites:
                        self.bt_favorites.remove(item_id)
                    else:
                        self.bt_favorites.add(item_id)
                else:
                    if item_id in self.wifi_favorites:
                        self.wifi_favorites.remove(item_id)
                    else:
                        self.wifi_favorites.add(item_id)
                self._update_list()
            elif action == "connect" and item_id:
                self._handle_connect_action(item_id)
        except Exception as e:
            print(f"Error: {e}")

    # ===== Bluetooth Methods =====

    def _start_bt_scan(self):
        """Start Bluetooth scan."""
        if self.bt_manager.state() == CBCentralManagerStatePoweredOn:
            self.bt_devices.clear()
            self.bt_peripherals.clear()
            self.bt_manager.scanForPeripheralsWithServices_options_(None, None)

    def _handle_connect_action(self, item_id: str):
        if self.mode == "bluetooth":
            peripheral = self.bt_peripherals.get(item_id)
            if peripheral is None:
                self.status.setStringValue_("Peripheral not available")
                return
            if self.bt_connected == item_id:
                self.bt_manager.cancelPeripheralConnection_(peripheral)
                self.status.setStringValue_("Disconnecting…")
                return
            self.status.setStringValue_(f"Connecting to {self.bt_devices[item_id][0]}…")
            self.bt_manager.connectPeripheral_options_(peripheral, None)
        else:
            try:
                interface = self.wifi_client.interface()
                if interface is None:
                    self.status.setStringValue_("WiFi interface unavailable")
                    return
                if self.wifi_connected == item_id:
                    if hasattr(interface, "disassociate"):
                        interface.disassociate()
                    self.wifi_connected = None
                    self.status.setStringValue_(f"Disconnected from {item_id}")
                    self._update_list()
                    return
                network = self.wifi_objects.get(item_id)
                if network is None:
                    self.status.setStringValue_("Network not available")
                    return
                self.status.setStringValue_(f"Connecting to {item_id}…")
                success, error = interface.associateToNetwork_password_error_(network, None, None)
                if success:
                    self.wifi_connected = item_id
                    self.status.setStringValue_(f"Connected to {item_id}")
                else:
                    error_msg = error.localizedDescription() if error else "Unknown"
                    self.status.setStringValue_(f"Failed to connect: {error_msg}")
                self._update_list()
            except Exception as e:
                self.status.setStringValue_(f"WiFi connect failed: {e}")

    def centralManagerDidUpdateState_(self, central):
        if central.state() == CBCentralManagerStatePoweredOn:
            self.status.setStringValue_("Bluetooth ready")
        else:
            self.status.setStringValue_("Bluetooth not available")

    def centralManager_didDiscoverPeripheral_advertisementData_RSSI_(
        self, _central, peripheral, advertisement_data, rssi
    ):
        identifier = str(peripheral.identifier())
        name = peripheral.name() or advertisement_data.get("kCBAdvDataLocalName") or "(unnamed)"
        self.bt_devices[identifier] = (str(name), int(rssi), datetime.now().strftime("%H:%M:%S"))
        self.bt_peripherals[identifier] = peripheral
        self._update_list()

    def centralManager_didConnectPeripheral_(self, central, peripheral):
        identifier = str(peripheral.identifier())
        self.bt_connected = identifier
        self._update_list()

    def centralManager_didFailToConnectPeripheral_error_(self, central, peripheral, error):
        identifier = str(peripheral.identifier())
        self.status.setStringValue_(f"Connection failed")
        self._update_list()

    def centralManager_didDisconnectPeripheral_error_(self, central, peripheral, error):
        identifier = str(peripheral.identifier())
        if self.bt_connected == identifier:
            self.bt_connected = None
        self._update_list()

    # ===== WiFi Methods =====

    def _start_wifi_scan(self):
        """Start WiFi scan."""
        try:
            interface = self.wifi_client.interface()
            if interface is None:
                self.status.setStringValue_("WiFi not available")
                return
            
            self.wifi_networks.clear()
            networks, _ = interface.scanForNetworksWithName_error_(None, None)
            
            if networks:
                for network in networks:
                    ssid = network.ssid() or "(Hidden)"
                    rssi = network.rssiValue()
                    security = self._get_security_string(network)
                    channel = f"Ch {network.wlanChannel().channelNumber()}" if network.wlanChannel() else "Unknown"
                    bssid = network.bssid() or "Unknown"
                    band = self._get_band_name(network)
                    width = self._get_channel_width(network)
                    self.wifi_networks[ssid] = (ssid, int(rssi), security, channel, bssid, band, width)
                    self.wifi_objects[ssid] = network
                
                self._update_list()
        except Exception as e:
            self.status.setStringValue_(f"WiFi scan error: {str(e)}")

    def _get_current_wifi(self):
        """Get current WiFi network."""
        try:
            interface = self.wifi_client.interface()
            if interface:
                self.wifi_connected = interface.ssid()
        except:
            pass

    @objc.python_method
    def _get_security_string(self, network) -> str:
        try:
            security_type = network.securityType()
            security_map = {0: "Open", 1: "WEP", 2: "WPA", 3: "WPA2", 4: "WPA3"}
            return security_map.get(security_type, "Unknown")
        except:
            return "Unknown"

    @objc.python_method
    def _get_band_name(self, network) -> str:
        try:
            channel = network.wlanChannel()
            if channel is None:
                return "Unknown"
            channel_number = channel.channelNumber()
            if channel_number <= 14:
                return "2.4 GHz"
            return "5 GHz"
        except:
            return "Unknown"

    @objc.python_method
    def _get_channel_width(self, network) -> str:
        try:
            channel = network.wlanChannel()
            if channel is None:
                return "Unknown"
            width = getattr(channel, 'width', None)
            if width is None:
                return "Unknown"
            return f"{width} MHz"
        except:
            return "Unknown"

    @objc.python_method
    def _get_signal_color(self, rssi: int) -> str:
        if rssi >= -50:
            return "#10b981"
        elif rssi >= -70:
            return "#3b82f6"
        elif rssi >= -80:
            return "#f59e0b"
        else:
            return "#ef4444"

    @objc.python_method
    def _get_signal_strength(self, rssi: int) -> int:
        percentage = max(0, min(100, (rssi + 100) * 2))
        return int(percentage)

    @objc.python_method
    def _get_ble_service_count(self, identifier: str) -> str:
        peripheral = self.bt_peripherals.get(identifier)
        if peripheral is None:
            return "Unknown"
        try:
            services = peripheral.services()
            if services is None:
                return "Not discovered"
            return str(len(services))
        except Exception:
            return "Unknown"

    @objc.python_method
    def _update_list(self):
        """Update list view."""
        theme_style = (
            "background: #111827; color: #e5e7eb;"
            if self.dark_mode
            else "background: #f9fafb; color: #111827;"
        )
        item_bg = "#1f2937" if self.dark_mode else "white"
        item_hover = "#374151" if self.dark_mode else "#f3f4f6"
        item_border = "#374151" if self.dark_mode else "#e5e7eb"
        text_muted = "#9ca3af" if self.dark_mode else "#6b7280"
        details_bg = "#111827" if self.dark_mode else "#f3f4f6"
        details_text = "#e5e7eb" if self.dark_mode else "#374151"

        html_parts = [
            f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, sans-serif; margin: 0; padding: 10px; {theme_style} }}
        .item-list {{ display: flex; flex-direction: column; gap: 8px; }}
        .item {{ background: {item_bg}; border: 1px solid {item_border}; border-radius: 6px; padding: 10px; 
                cursor: pointer; transition: all 0.2s; }}
        .item:hover {{ background: {item_hover}; border-color: #9ca3af; }}
        .item.selected {{ background: #2563eb; border-color: #1d4ed8; color: white; }}
        .item-name {{ font-weight: 600; font-size: 13px; }}
        .item-info {{ font-size: 11px; color: {text_muted}; margin-top: 4px; }}
        .signal-bar {{ height: 4px; background: #e5e7eb; border-radius: 2px; margin-top: 4px; }}
        .signal-fill {{ height: 100%; border-radius: 2px; }}
        .badges {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }}
        .badge {{ font-size: 10px; padding: 2px 4px; background: #e5e7eb; border-radius: 3px; }}
        .badge.fav {{ background: #fef3c7; }}
        .badge.conn {{ background: #d1fae5; }}
        .item-details {{ margin-top: 8px; padding: 10px; background: {details_bg}; border-radius: 6px; font-size: 12px; color: {details_text}; }}
        .item-details div {{ margin-bottom: 4px; }}
        .btn-fav, .btn-action {{ font-size: 12px; cursor: pointer; margin-top: 8px; padding: 6px 8px; border: 1px solid #d1d5db; border-radius: 4px; background: #f9fafb; color: #111827; }}
        .btn-action {{ background: #3b82f6; color: white; border-color: #3b82f6; margin-left: 8px; }}
        .btn-action:hover {{ background: #2563eb; }}
        .btn-fav:hover {{ background: #e5e7eb; }}
    </style>
</head>
<body>
    <div class="item-list">
<script>
function selectItem(id) {{
    webkit.messageHandlers.deviceAction.postMessage(JSON.stringify({{ action: "select", item_id: id }}));
}}
function toggleFav(id, e) {{
    e.stopPropagation();
    webkit.messageHandlers.deviceAction.postMessage(JSON.stringify({{ action: "toggle_favorite", item_id: id }}));
}}
function connectItem(id, e) {{
    e.stopPropagation();
    webkit.messageHandlers.deviceAction.postMessage(JSON.stringify({{ action: "connect", item_id: id }}));
}}
</script>
''']

        if self.mode == "bluetooth":
            items = list(self.bt_devices.items())
            if self.filter_mode == "favorites":
                items = [item for item in items if item[0] in self.bt_favorites]
            elif self.filter_mode == "connected":
                items = [item for item in items if item[0] == self.bt_connected]

            if self.sort_mode == "name":
                items.sort(key=lambda x: x[1][0].lower())
            elif self.sort_mode == "connected":
                items.sort(key=lambda x: x[0] != self.bt_connected)
            else:
                items.sort(key=lambda x: x[1][1], reverse=True)

            for identifier, (name, rssi, last_seen) in items:
                is_selected = identifier == self.selected_device
                is_fav = identifier in self.bt_favorites
                is_conn = identifier == self.bt_connected
                
                signal_color = self._get_signal_color(rssi)
                signal_strength = self._get_signal_strength(rssi)
                
                cls = "item selected" if is_selected else "item"
                details_html = ""
                if is_selected:
                    connected_text = "Disconnect" if is_conn else "Connect"
                    details_html = f'''            <div class="item-details">
                <div><strong>Identifier:</strong> {identifier}</div>
                <div><strong>Last Seen:</strong> {last_seen}</div>
                <div><strong>Status:</strong> {'🔗 Connected' if is_conn else '❌ Disconnected'}</div>
                <div><strong>Favorite:</strong> {'⭐ Yes' if is_fav else '☆ No'}</div>
                <div><strong>Services:</strong> {self._get_ble_service_count(identifier)}</div>
                <div><button class="btn-action" onclick="connectItem('{identifier}', event)">{connected_text}</button></div>
            </div>'''
                html_parts.append(f'''        <div class="{cls}" onclick="selectItem('{identifier}')">
            <div class="item-name">📱 {name}</div>
            <div class="item-info">RSSI: {rssi} dBm | {last_seen}</div>
            <div class="signal-bar"><div class="signal-fill" style="width: {signal_strength}%; background: {signal_color};"></div></div>
            <div class="badges">
                {f'<span class="badge conn">✓ Connected</span>' if is_conn else ''}
                {f'<span class="badge fav">⭐ Favorite</span>' if is_fav else ''}
            </div>
            {details_html}
            <div class="btn-fav" onclick="toggleFav('{identifier}', event)">{'☆ Add to favorites' if not is_fav else '⭐ Remove from favorites'}</div>
        </div>
''')
        else:
            items = list(self.wifi_networks.items())
            if self.filter_mode == "favorites":
                items = [item for item in items if item[0] in self.wifi_favorites]
            elif self.filter_mode == "connected":
                items = [item for item in items if item[0] == self.wifi_connected]

            if self.sort_mode == "name":
                items.sort(key=lambda x: x[0].lower())
            elif self.sort_mode == "connected":
                items.sort(key=lambda x: x[0] != self.wifi_connected)
            else:
                items.sort(key=lambda x: x[1][1], reverse=True)

            for ssid, (_, rssi, security, channel, bssid, band, width) in items:
                is_selected = ssid == self.selected_device
                is_fav = ssid in self.wifi_favorites
                is_conn = ssid == self.wifi_connected
                
                signal_color = self._get_signal_color(rssi)
                signal_strength = self._get_signal_strength(rssi)
                
                cls = "item selected" if is_selected else "item"
                details_html = ""
                if is_selected:
                    connected_text = "Disconnect" if is_conn else "Connect"
                    details_html = f'''            <div class="item-details">
                <div><strong>SSID:</strong> {ssid}</div>
                <div><strong>Security:</strong> {security}</div>
                <div><strong>Channel:</strong> {channel}</div>
                <div><strong>Band:</strong> {band}</div>
                <div><strong>Width:</strong> {width}</div>
                <div><strong>BSSID:</strong> {bssid}</div>
                <div><strong>Status:</strong> {'🔗 Connected' if is_conn else 'Not connected'}</div>
                <div><strong>Favorite:</strong> {'⭐ Yes' if is_fav else '☆ No'}</div>
                <div><button class="btn-action" onclick="connectItem('{ssid}', event)">{connected_text}</button></div>
            </div>'''
                html_parts.append(f'''        <div class="{cls}" onclick="selectItem('{ssid}')">
            <div class="item-name">📡 {ssid}</div>
            <div class="item-info">{security} • {channel} • {rssi} dBm</div>
            <div class="signal-bar"><div class="signal-fill" style="width: {signal_strength}%; background: {signal_color};"></div></div>
            <div class="badges">
                {f'<span class="badge conn">✓ Connected</span>' if is_conn else ''}
                {f'<span class="badge fav">⭐ Favorite</span>' if is_fav else ''}
            </div>
            {details_html}
            <div class="btn-fav" onclick="toggleFav('{ssid}', event)">{'☆ Add to favorites' if not is_fav else '⭐ Remove from favorites'}</div>
        </div>
''')
        
        html_parts.append('    </div>\n</body>\n</html>')
        self.list_view.loadHTMLString_baseURL_("".join(html_parts), NSURL.fileURLWithPath_("/"))


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    controller = CombinedScannerWindow.alloc().init()
    controller.window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)
    app.run()


if __name__ == "__main__":
    main()
