# Bluetooth scanner for macOS

This script finds nearby **Bluetooth Low Energy (BLE)** devices on a MacBook Air.
It uses Apple's CoreBluetooth framework, so it works with the Bluetooth hardware
already in macOS.

## Run it

Open **Terminal**, then run:

```zsh
cd /Users/dattatraybhairi/Documents/bluetooth_scanner
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scan_bluetooth.py
```

The pip upgrade is important when using Apple's bundled Python 3.9: it lets pip
select the compatible prebuilt PyObjC wheel instead of trying to compile one.

When asked, allow Terminal (or your Python app) to use Bluetooth. You can later
change this under **System Settings → Privacy & Security → Bluetooth**.

Press `Ctrl-C` to stop. To print every repeated advertisement (useful for
watching RSSI changes), run:

```zsh
python scan_bluetooth.py --duplicates
```

## Run the graphical app

With the virtual environment still active, launch the native macOS window:

```zsh
python bluetooth_scanner_ui.py
```

Click **Start Scan** to find devices. The list is refreshed as each device
advertises, with its current signal strength and last-seen time.

## Notes

- Turn Bluetooth on in Control Center before running the program.
- Modern Apple privacy rules do not provide Bluetooth MAC addresses. The `id`
  shown is a UUID assigned by macOS.
- CoreBluetooth only discovers BLE advertisements. Classic Bluetooth devices
  that do not advertise BLE may not appear.

## iPhone app: repeated advertisement metrics

The [iOS source folder](ios/BluetoothDuplicateScanner) contains a SwiftUI app
that groups discoveries by iOS device UUID. It intentionally enables repeated
BLE advertisements and records, for every device: advertisement count, current,
minimum, maximum, and average RSSI, plus last-seen time.

To run it, open Xcode on a Mac, create a new **iOS App** named
`BluetoothDuplicateScanner` (SwiftUI), then replace the generated Swift files
and `Info.plist` with the files in that folder. Select a physical iPhone as the
run destination; the iOS Simulator cannot scan Bluetooth LE devices. Allow
Bluetooth access when iOS prompts you.

### Test the iPhone app without Bluetooth hardware

The simulator sends made-up advertisement events over your local Wi-Fi; it does
not transmit Bluetooth or imitate a real product.

1. On the Mac, run `python3 demo_advertisements_server.py`.
2. Find the Mac's Wi-Fi address with `ipconfig getifaddr en0`.
3. Connect the iPhone to the same Wi-Fi network.
4. In the iPhone app, enable **Use Python simulator**, enter
   `http://YOUR_MAC_IP:8765/advertisement`, then tap **Start**.

The `ads` number should repeatedly increase for the three simulated devices.
This mode permits HTTP only for local development; remove the App Transport
Security exception in `Info.plist` before distributing an app.

### Broadcast a real, generic BLE test beacon from the Mac

The following command broadcasts a clearly custom BLE name and UUID. macOS
handles repeated advertising automatically; it does not permit Python to create
arbitrary raw BLE packets or impersonate another product.

```zsh
source .venv/bin/activate
python advertise_ble_beacon.py
```

Use a different custom name or service UUID if needed:

```zsh
python advertise_ble_beacon.py --name "StudyBeacon-02" --uuid "87654321-4321-4321-4321-BA0987654321"
```

Allow Bluetooth access for Terminal if macOS requests it. Keep the Mac awake
and the program running while scanning from the iPhone. Press `Ctrl-C` to stop.
