import SwiftUI

struct ContentView: View {
    @StateObject private var scanner = BluetoothScanner()

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text(scanner.status)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Section("Data source") {
                    Toggle("Use Python simulator", isOn: $scanner.usesSimulator)
                        .disabled(scanner.isScanning)
                    if scanner.usesSimulator {
                        TextField("Simulator URL", text: $scanner.simulatorURL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                            .font(.caption)
                    }
                }

                Section("Nearby BLE devices") {
                    if scanner.devices.isEmpty {
                        ContentUnavailableView(
                            "No devices yet",
                            systemImage: "dot.radiowaves.left.and.right",
                            description: Text("Start a scan to count each device's repeated advertisements.")
                        )
                    }

                    ForEach(scanner.devices) { device in
                        DeviceRow(device: device)
                    }
                }
            }
            .navigationTitle("BLE Duplicates")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Clear", action: scanner.clear)
                        .disabled(scanner.devices.isEmpty)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button(scanner.isScanning ? "Stop" : "Start") {
                        scanner.isScanning ? scanner.stop() : scanner.start()
                    }
                    .fontWeight(.semibold)
                }
            }
        }
    }
}

private struct DeviceRow: View {
    let device: DiscoveredDevice

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(device.name).font(.headline)
                Spacer()
                Text("\(device.advertisementCount) ads")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.blue)
            }
            Text(device.signalSummary)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text("Range \(device.minimumRSSI)…\(device.maximumRSSI) dBm · \(device.id.uuidString)")
                .font(.caption2)
                .foregroundStyle(.tertiary)
                .lineLimit(1)
        }
        .padding(.vertical, 3)
    }
}
