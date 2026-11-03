#if DEBUG && targetEnvironment(simulator)
import Foundation
import PrettyLisaCore

/// Never compiled for physical devices, macOS or Release. Does not allocate backend leases.
@MainActor final class SimulatorVPNController: VPNControlling {
    private(set) var state: ConnectionState = .disconnected { didSet { onChange?() } }
    var onChange: (() -> Void)?
    private var transition: Task<Void, Never>?
    func connect(country: String, methods: [String]) {
        guard transition == nil, !state.protected else { return }
        state = .connecting("WireGuard")
        transition = Task {
            defer { transition = nil }
            do { try await Task.sleep(nanoseconds: 1_000_000_000); state = .connected("WireGuard") }
            catch { }
        }
    }
    func disconnect() async {
        transition?.cancel(); await transition?.value; transition = nil
        state = .disconnecting
        try? await Task.sleep(nanoseconds: 400_000_000)
        state = .disconnected
    }
    func select(_ state: ConnectionState) { transition?.cancel(); transition = nil; self.state = state }
}
#endif
