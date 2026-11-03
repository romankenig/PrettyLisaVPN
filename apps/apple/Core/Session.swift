import Foundation

public protocol CredentialStore: Sendable {
    func read() throws -> Credentials?
    func write(_ credentials: Credentials) throws
    func clear() throws
}

/// Actor reentrancy alone does not serialize token rotation. All credential transitions share this gate.
actor SerialGate {
    private var held = false
    private var waiters: [CheckedContinuation<Void, Never>] = []
    func run<T>(_ body: () async throws -> T) async rethrows -> T {
        if held { await withCheckedContinuation { waiters.append($0) } } else { held = true }
        defer {
            if waiters.isEmpty { held = false } else { waiters.removeFirst().resume() }
        }
        return try await body()
    }
}

public actor Session {
    public let api: API
    private let store: any CredentialStore
    private let gate = SerialGate()
    public init(api: API, store: any CredentialStore) { self.api = api; self.store = store }

    public func requestOTP(email: String) async throws {
        _ = try await api.data("auth/request-otp", method: "POST", body: WireJSON.encode(["email": email]))
    }
    public func login(email: String, code: String, installation: UUID, platform: String, name: String) async throws {
        try await gate.run {
            let data = try await self.api.data("auth/verify-otp", method: "POST", body: WireJSON.encode([
                "email": email, "code": code, "installation_id": installation.uuidString.lowercased(),
                "platform": platform, "device_name": name]))
            try self.accept(WireJSON.decode(Tokens.self, from: data))
        }
    }
    private func accept(_ tokens: Tokens) throws {
        try tokens.validate()
        try store.write(Credentials(tokens: tokens))
    }
    private func bearer(forceRefresh: Bool = false) async throws -> String {
        guard var stored = try store.read() else { throw ClientError("REAUTH_REQUIRED") }
        guard !stored.rotationPending else { throw ClientError("ROTATION_UNCERTAIN") }
        guard let expiry = WireJSON.date(stored.tokens.refresh_token_expires_at), expiry > Date() else {
            try store.clear(); throw ClientError("REAUTH_REQUIRED")
        }
        if !forceRefresh && stored.accessUntil > Date() { return stored.tokens.access_token }
        stored.rotationPending = true
        try store.write(stored) // Crash/timeout fence: never replay a consumed refresh credential.
        do {
            let data = try await api.data("auth/refresh", method: "POST", body: WireJSON.encode([
                "session_id": stored.tokens.session_id.uuidString.lowercased(), "refresh_token": stored.tokens.refresh_token]))
            let fresh = try WireJSON.decode(Tokens.self, from: data)
            guard fresh.session_id == stored.tokens.session_id else { throw ClientError("ROTATION_UNCERTAIN") }
            try accept(fresh)
            return fresh.access_token
        } catch let error as ClientError {
            if error.status == 401 || error.status == 403 { try store.clear() }
            // Even a 5xx is ambiguous; only a new OTP can recover a pending rotation.
            throw error
        }
    }
    public func request(_ path: String, method: String = "GET", body: Data? = nil,
                        headers: [String: String] = [:], query: [URLQueryItem] = []) async throws -> Data {
        try await gate.run {
            do {
                return try await self.perform(path, method: method, body: body, headers: headers, query: query)
            } catch let error as ClientError {
                if error.status == 403 && error.terminal { try self.store.clear() }
                throw error
            }
        }
    }
    private func perform(_ path: String, method: String, body: Data?, headers: [String: String], query: [URLQueryItem]) async throws -> Data {
        let token = try await bearer()
        do { return try await api.data(path, method: method, body: body, token: token, headers: headers, query: query) }
        catch let error as ClientError where error.status == 401 {
            let replacement = try await bearer(forceRefresh: true)
            // Explicit 401 proves the authenticated action was not accepted; no replay on timeout.
            do { return try await api.data(path, method: method, body: body, token: replacement, headers: headers, query: query) }
            catch let failure as ClientError where failure.status == 401 { try store.clear(); throw ClientError("REAUTH_REQUIRED") }
        }
    }
    public func hasCredentials() throws -> Bool { try store.read() != nil }
    public func forget() async throws { try await gate.run { try self.store.clear() } }
    public func logout() async throws {
        try await gate.run {
            do {
                _ = try await self.perform("auth/logout", method: "POST", body: Data("{}".utf8), headers: [:], query: [])
            } catch let error as ClientError {
                guard error.terminal || error.status == 401 else { throw error }
            }
            try self.store.clear()
        }
    }
}
