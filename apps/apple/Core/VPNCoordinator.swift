import Foundation

public enum DriverStatus: String, Sendable { case down, starting, up, reasserting, stopping }
public enum ConnectionState: Equatable, Sendable {
    case disconnected, connecting(String), verifying, connected(String), reconnecting, disconnecting, failed(String)
    public var protected: Bool { if case .connected = self { return true }; return false }
}
@MainActor public protocol TunnelDriver: AnyObject {
    var status: DriverStatus { get }
    var leaseID: UUID? { get }
    var onStatus: (() -> Void)? { get set }
    func reload() async throws
    func start(_ payload: TunnelPayload) async throws
    func stop() async throws
    func hasTraffic() async throws -> Bool
}

@MainActor public final class VPNCoordinator {
    public private(set) var state: ConnectionState = .disconnected { didSet { onChange?() } }
    public private(set) var lease: Lease?
    public private(set) var verifiedIP: String?
    public var onChange: (() -> Void)?
    public var onAuthorizationLost: (() -> Void)?
    private let session: Session
    private let driver: any TunnelDriver
    private let keyPair: () -> (privateKey: String, publicKey: String)
    private var operation: Task<Void, Never>?
    private var checkTask: Task<Void, Never>?
    private var checkID: UUID?
    private var stopping = false
    public var busy: Bool { operation != nil || stopping || checkTask != nil }
    public var localTunnelDown: Bool { driver.status == .down }
    public init(session: Session, driver: any TunnelDriver, keyPair: @escaping () -> (String, String)) {
        self.session = session; self.driver = driver; self.keyPair = keyPair
        driver.onStatus = { [weak self] in self?.statusChanged() }
    }
    private func row(_ suffix: String) async throws -> Lease? {
        try WireJSON.decode(Lease?.self, from: await session.request("vpn/sessions/" + suffix))
    }
    private func statusChanged() {
        guard !stopping, operation == nil else { return }
        switch driver.status {
        case .reasserting: state = .reconnecting; verifiedIP = nil
        case .down:
            if state.protected || state == .reconnecting || state == .verifying {
                state = .failed("TUNNEL_STOPPED"); verifiedIP = nil
            }
        case .up:
            if operation == nil { Task { await self.reconcile() } }
        default: break
        }
    }
    public func connect(country: String, methods: [String]) {
        guard !busy else { return }
        guard !methods.isEmpty, methods.allSatisfy(Methods.all.contains),
              country.range(of: "^(AUTO|[A-Z]{2})$", options: .regularExpression) != nil else {
            state = .failed("INVALID_SELECTION"); return
        }
        operation = Task {
            defer { operation = nil }
            do {
                try await cleanup()
                var lastCode = "VPN_UNAVAILABLE"
                for method in methods {
                    try Task.checkCancellation()
                    state = .connecting(method)
                    do {
                        try await attempt(country: country, method: method)
                        return
                    } catch {
                        lastCode = (error as? ClientError)?.code ?? "CONNECTION_FAILED"
                        // Also discovers a peer whose POST response was lost; never allocate over an uncertain peer.
                        try await Task { try await self.cleanup() }.value
                        try Task.checkCancellation()
                        if let failure = error as? ClientError,
                           failure.terminal || ["FREE_QUOTA_EXHAUSTED", "COUNTRY_UNAVAILABLE", "UNSUPPORTED_CONFIGURATION"].contains(failure.code) {
                            throw failure
                        }
                    }
                }
                throw ClientError(lastCode)
            } catch is CancellationError { }
            catch { state = .failed((error as? ClientError)?.code ?? "CONNECTION_FAILED") }
        }
    }
    private func attempt(country: String, method: String) async throws {
        let keys = keyPair()
        let data = try await session.request("vpn/sessions", method: "POST", body: WireJSON.encode([
            "country": country, "method": method, "public_key": keys.publicKey
        ]), headers: ["Idempotency-Key": UUID().uuidString.lowercased()])
        lease = try WireJSON.decode(Lease.self, from: data)
        guard let identifier = lease?.id else { throw ClientError("INVALID_RESPONSE") }
        let limit = Date().addingTimeInterval(65)
        while lease?.status == .PROVISIONING && Date() < limit {
            try await Task.sleep(nanoseconds: 1_000_000_000)
            lease = try await row(identifier.uuidString.lowercased())
        }
        guard let ready = lease, ready.id == identifier, ready.method == method else { throw ClientError("VPN_SETUP_FAILED") }
        let payload = try TunnelPayload.make(lease: ready, privateKey: keys.privateKey, apiBase: session.api.base)
        try Task.checkCancellation()
        try await driver.start(payload)
        state = .verifying
        let end = Date().addingTimeInterval(35)
        while Date() < end {
            try Task.checkCancellation()
            if driver.status == .up {
                do { try await verify(ready); state = .connected(method); return }
                catch let error as ClientError where error.terminal { throw error }
                catch { }
            }
            if driver.status == .down { throw ClientError("TUNNEL_START_FAILED") }
            try await Task.sleep(nanoseconds: 1_000_000_000)
        }
        throw ClientError("INTERNET_UNVERIFIED")
    }
    private func verify(_ row: Lease) async throws {
        guard row.deadline.map({ $0 > Date() }) == true, row.status == .READY,
              let expected = row.configuration?.expected_egress_ips,
              driver.status == .up, driver.leaseID == row.id else { throw ClientError("TUNNEL_UNAVAILABLE") }
        let data = try await session.request("vpn/sessions/\(row.id.uuidString.lowercased())/probe",
                                             query: [URLQueryItem(name: "nonce", value: UUID().uuidString)])
        let proof = try WireJSON.decode(Probe.self, from: data)
        guard proof.verified, expected.contains(proof.ip), try await driver.hasTraffic(),
              driver.status == .up else { throw ClientError("EGRESS_MISMATCH") }
        verifiedIP = proof.ip
    }
    public func reconcile() async {
        guard !busy else { return }
        let id = UUID()
        let task = Task { await self.reconcileState() }
        checkTask = task; checkID = id
        await task.value
        if checkID == id { checkTask = nil; checkID = nil }
    }
    private func reconcileState() async {
        do {
            try await driver.reload()
            try Task.checkCancellation()
            lease = try await row("current")
            try Task.checkCancellation()
            guard let current = lease else {
                if driver.status != .down { try await driver.stop() }
                state = .disconnected; verifiedIP = nil; return
            }
            guard current.id == driver.leaseID, driver.status != .down,
                  current.status == .READY, current.deadline.map({ $0 > Date() }) == true else {
                try await cleanup(); state = .disconnected; return
            }
            if driver.status == .reasserting { state = .reconnecting; return }
            state = .verifying
            try await verify(current)
            try Task.checkCancellation()
            state = .connected(current.method)
        } catch is CancellationError { return
        } catch let error as ClientError where error.terminal || error.status == 403 {
            // An ambiguous refresh is not proof of server revocation. Keep OS tunnel visible, ask for OTP.
            if error.code != "ROTATION_UNCERTAIN" { try? await driver.stop() }
            state = .failed(error.code); verifiedIP = nil; onAuthorizationLost?()
        } catch {
            if driver.status != .down { state = .reconnecting } else { state = .failed((error as? ClientError)?.code ?? "NETWORK_UNCERTAIN") }
            verifiedIP = nil
        }
    }
    public func disconnect() async {
        guard !stopping else { return }
        stopping = true
        state = .disconnecting
        operation?.cancel()
        checkTask?.cancel()
        await checkTask?.value
        checkTask = nil; checkID = nil
        await operation?.value
        operation = nil
        do { try await cleanup(); state = .disconnected }
        catch { state = .failed((error as? ClientError)?.code ?? "CLEANUP_UNCONFIRMED") }
        stopping = false
    }
    private func cleanup() async throws {
        verifiedIP = nil
        try await driver.stop()
        let current: Lease?
        if let known = lease { current = known } else { current = try await row("current") }
        guard let current else { return }
        let path = current.id.uuidString.lowercased()
        if current.status != .CLOSED {
            _ = try await session.request("vpn/sessions/" + path, method: "DELETE")
            let limit = Date().addingTimeInterval(35)
            // Cleanup deliberately completes after connect cancellation.
            while Date() < limit {
                if try await row(path)?.status == .CLOSED { lease = nil; return }
                await withCheckedContinuation { continuation in
                    DispatchQueue.global().asyncAfter(deadline: .now() + 1) { continuation.resume() }
                }
            }
            throw ClientError("CLEANUP_UNCONFIRMED")
        }
        lease = nil
    }
}
