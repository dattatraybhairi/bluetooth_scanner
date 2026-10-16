import CoreBluetooth
import Foundation

/// One nearby BLE peripheral, aggregated by the UUID assigned by iOS.
struct DiscoveredDevice: Identifiable {
    let id: UUID
    var name: String
    var advertisementCount: Int
    var lastRSSI: Int
    var minimumRSSI: Int
    var maximumRSSI: Int
    var averageRSSI: Double
    var lastSeen: Date

    var signalSummary: String {
        "Last \(lastRSSI) dBm · Avg \(Int(averageRSSI)) dBm"
    }
}

final class BluetoothScanner: NSObject, ObservableObject {
    @Published private(set) var devices: [DiscoveredDevice] = []
    @Published private(set) var isScanning = false
    @Published private(set) var status = "Preparing Bluetooth…"
    @Published var usesSimulator = false
    @Published var simulatorURL = "http://192.168.1.10:8765/advertisement"

    private var central: CBCentralManager!
    private var deviceIndex: [UUID: DiscoveredDevice] = [:]
    private var simulatorTimer: Timer?

    override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: .main)
    }

    func start() {
        if usesSimulator {
            startSimulator()
            return
        }
        guard central.state == .poweredOn else {
            status = "Bluetooth is not ready. Turn it on and allow access."
            return
        }
        // This option is the key feature: iOS delivers every advertisement,
        // including repeats from a device UUID already discovered.
        central.scanForPeripherals(
            withServices: nil,
            options: [CBCentralManagerScanOptionAllowDuplicatesKey: true]
        )
        isScanning = true
        status = "Scanning for repeated BLE advertisements…"
    }

    func stop() {
        central.stopScan()
        simulatorTimer?.invalidate()
        simulatorTimer = nil
        isScanning = false
        status = "Stopped — \(devices.count) unique device(s) found."
    }

    func clear() {
        deviceIndex.removeAll()
        devices = []
        status = "Results cleared."
    }

    private func publishDevices() {
        devices = deviceIndex.values.sorted {
            if $0.advertisementCount == $1.advertisementCount {
                return $0.lastSeen > $1.lastSeen
            }
            return $0.advertisementCount > $1.advertisementCount
        }
    }

    private func startSimulator() {
        guard URL(string: simulatorURL) != nil else {
            status = "Enter a valid simulator URL."
            return
        }
        simulatorTimer?.invalidate()
        isScanning = true
        status = "Receiving simulated advertisements…"
        simulatorTimer = Timer.scheduledTimer(withTimeInterval: 0.65, repeats: true) { [weak self] _ in
            self?.requestSimulatedAdvertisement()
        }
        requestSimulatedAdvertisement()
    }

    private func requestSimulatedAdvertisement() {
        guard let url = URL(string: simulatorURL) else { return }
        URLSession.shared.dataTask(with: url) { [weak self] data, _, _ in
            guard let data, let event = try? JSONDecoder().decode(SimulatedAdvertisement.self, from: data) else {
                DispatchQueue.main.async { self?.status = "Could not reach the simulator URL." }
                return
            }
            DispatchQueue.main.async { self?.recordAdvertisement(id: event.id, name: event.name, rssi: event.rssi) }
        }.resume()
    }

    private func recordAdvertisement(id: UUID, name: String, rssi: Int) {
        let now = Date()
        if var device = deviceIndex[id] {
            let count = device.advertisementCount + 1
            device.name = name
            device.advertisementCount = count
            device.lastRSSI = rssi
            device.minimumRSSI = min(device.minimumRSSI, rssi)
            device.maximumRSSI = max(device.maximumRSSI, rssi)
            device.averageRSSI += (Double(rssi) - device.averageRSSI) / Double(count)
            device.lastSeen = now
            deviceIndex[id] = device
        } else {
            deviceIndex[id] = DiscoveredDevice(
                id: id, name: name, advertisementCount: 1, lastRSSI: rssi,
                minimumRSSI: rssi, maximumRSSI: rssi, averageRSSI: Double(rssi), lastSeen: now
            )
        }
        publishDevices()
        status = "\(usesSimulator ? "Simulating" : "Scanning") — \(devices.count) unique device(s)."
    }
}

private struct SimulatedAdvertisement: Decodable {
    let id: UUID
    let name: String
    let rssi: Int
}

extension BluetoothScanner: CBCentralManagerDelegate {
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        switch central.state {
        case .poweredOn:
            status = "Bluetooth ready. Tap Start Scan."
        case .poweredOff:
            status = "Bluetooth is turned off."
        case .unauthorized:
            status = "Bluetooth permission was not granted."
        case .unsupported:
            status = "Bluetooth LE is not supported on this device."
        case .resetting:
            status = "Bluetooth is resetting…"
        default:
            status = "Bluetooth status is unknown."
        }
    }

    func centralManager(
        _ central: CBCentralManager,
        didDiscover peripheral: CBPeripheral,
        advertisementData: [String: Any],
        rssi RSSI: NSNumber
    ) {
        let id = peripheral.identifier
        let name = peripheral.name
            ?? advertisementData[CBAdvertisementDataLocalNameKey] as? String
            ?? "Unnamed device"
        let rssi = RSSI.intValue
        recordAdvertisement(id: id, name: name, rssi: rssi)
    }
}
