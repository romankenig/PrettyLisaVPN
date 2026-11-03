import Foundation
import NetworkExtension
import PrettyLisaCore

@MainActor final class NetworkTunnelDriver: TunnelDriver {
    private var manager: NETunnelProviderManager?
    private let store: KeychainStore
    private let extensionID: String
    private var observer: NSObjectProtocol?
    var onStatus: (() -> Void)?
    var leaseID: UUID? {
        ((manager?.protocolConfiguration as? NETunnelProviderProtocol)?.providerConfiguration?["leaseID"] as? String).flatMap(UUID.init(uuidString:))
    }
    var status: DriverStatus {
        switch manager?.connection.status {
        case .connected: return .up
        case .connecting: return .starting
        case .reasserting: return .reasserting
        case .disconnecting: return .stopping
        default: return .down
        }
    }
    init(store: KeychainStore, extensionID: String) {
        self.store = store; self.extensionID = extensionID
        observer = NotificationCenter.default.addObserver(forName: .NEVPNStatusDidChange, object: nil, queue: .main) { [weak self] notification in
            Task { @MainActor in
                guard let self, let connection = notification.object as? NEVPNConnection, connection === self.manager?.connection else { return }
                self.onStatus?()
            }
        }
    }
    deinit { if let observer { NotificationCenter.default.removeObserver(observer) } }
    func reload() async throws {
        #if targetEnvironment(simulator)
        throw ClientError("PHYSICAL_DEVICE_REQUIRED")
        #else
        let managers = try await NETunnelProviderManager.loadAllFromPreferences()
        let owned = managers.filter { ($0.protocolConfiguration as? NETunnelProviderProtocol)?.providerBundleIdentifier == extensionID }
        guard owned.count <= 1 else { throw ClientError("DUPLICATE_VPN_PROFILE") }
        manager = owned.first
        #endif
    }
    func start(_ payload: TunnelPayload) async throws {
        #if targetEnvironment(simulator)
        throw ClientError("PHYSICAL_DEVICE_REQUIRED")
        #else
        try await reload()
        guard status == .down else { throw ClientError("TUNNEL_BUSY") }
        try store.save(WireJSON.encode(payload), account: "tunnel")
        let tunnel = NETunnelProviderProtocol()
        tunnel.providerBundleIdentifier = extensionID
        tunnel.serverAddress = "PrettyLisaVPN"
        tunnel.passwordReference = try store.persistentReference("tunnel")
        tunnel.providerConfiguration = ["leaseID": payload.leaseID.uuidString.lowercased()]
        tunnel.disconnectOnSleep = false
        // Explicit routes in the provider capture IPv4/IPv6. Apple-reserved system traffic remains OS-owned.
        tunnel.includeAllNetworks = false
        let manager = manager ?? NETunnelProviderManager()
        manager.protocolConfiguration = tunnel
        manager.localizedDescription = "PrettyLisaVPN"
        manager.isEnabled = true
        manager.isOnDemandEnabled = false
        try await manager.saveToPreferences()
        try await manager.loadFromPreferences()
        self.manager = manager
        guard let connection = manager.connection as? NETunnelProviderSession else { throw ClientError("TUNNEL_UNAVAILABLE") }
        try connection.startTunnel()
        #endif
    }
    func stop() async throws {
        #if !targetEnvironment(simulator)
        if manager == nil { try await reload() }
        manager?.connection.stopVPNTunnel()
        let deadline = Date().addingTimeInterval(15)
        while status != .down && Date() < deadline {
            await withCheckedContinuation { continuation in
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { continuation.resume() }
            }
        }
        guard status == .down else { throw ClientError("LOCAL_TEARDOWN_UNCONFIRMED") }
        try store.delete("tunnel")
        #endif
    }
    func hasTraffic() async throws -> Bool {
        guard status == .up, let connection = manager?.connection as? NETunnelProviderSession else { return false }
        return try await withCheckedThrowingContinuation { continuation in
            let reply = SingleReply(continuation)
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) { reply.finish(.failure(ClientError("EXTENSION_TIMEOUT"))) }
            do {
                try connection.sendProviderMessage(Data("status".utf8)) { data in
                    struct Stats: Decodable { let running: Bool; let received: UInt64; let sent: UInt64 }
                    guard let data, let stats = try? JSONDecoder().decode(Stats.self, from: data) else {
                        reply.finish(.failure(ClientError("EXTENSION_UNAVAILABLE"))); return
                    }
                    reply.finish(.success(stats.running && stats.received > 0 && stats.sent > 0))
                }
            } catch { reply.finish(.failure(ClientError("EXTENSION_UNAVAILABLE"))) }
        }
    }
}

final class SingleReply<T>: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<T, Error>?
    init(_ continuation: CheckedContinuation<T, Error>) { self.continuation = continuation }
    func finish(_ result: Result<T, Error>) {
        lock.lock(); let value = continuation; continuation = nil; lock.unlock()
        value?.resume(with: result)
    }
}
