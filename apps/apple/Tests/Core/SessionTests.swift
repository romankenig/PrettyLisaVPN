import XCTest
@testable import PrettyLisaCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class MemoryCredentials: CredentialStore, @unchecked Sendable {
    private let lock = NSLock()
    private var value: Credentials?
    init(_ value: Credentials? = nil) { self.value = value }
    func read() throws -> Credentials? { lock.lock(); defer { lock.unlock() }; return value }
    func write(_ credentials: Credentials) throws { lock.lock(); defer { lock.unlock() }; value = credentials }
    func clear() throws { lock.lock(); defer { lock.unlock() }; value = nil }
}
actor AuthTransport: HTTPTransport {
    var refreshes = 0
    var forceTimeout = false
    var rejectBearer = false
    func timeout() { forceTimeout = true }
    func reject() { rejectBearer = true }
    func send(_ request: URLRequest) async throws -> (Data, Int) {
        if request.url!.path == "/auth/refresh" {
            refreshes += 1
            try await Task.sleep(nanoseconds: 20_000_000)
            if forceTimeout { throw ClientError("TIMEOUT") }
            return (try WireJSON.encode(tokens(access: "fresh")), 200)
        }
        if rejectBearer && request.value(forHTTPHeaderField: "Authorization") != "Bearer fresh" {
            return (Data(#"{"error":{"code":"invalid_access_token"}}"#.utf8), 401)
        }
        return (Data("{}".utf8), 200)
    }
}
func tokens(access: String = "old") -> Tokens {
    Tokens(access_token: access, refresh_token: "test-only-refresh", session_id: UUID(uuidString: "11111111-1111-4111-8111-111111111111")!,
           access_token_expires_in: 3600, refresh_token_expires_at: "2099-01-01T00:00:00Z", token_type: "bearer")
}
final class SessionTests: XCTestCase {
    func testConcurrentReadsRotateExactlyOnce() async throws {
        var stored = Credentials(tokens: tokens()); stored.accessUntil = .distantPast
        let vault = MemoryCredentials(stored), transport = AuthTransport()
        let session = Session(api: try API(base: URL(string: "https://api.example.com")!, transport: transport), store: vault)
        try await withThrowingTaskGroup(of: Void.self) { group in
            for _ in 0..<12 { group.addTask { _ = try await session.request("me") } }
            try await group.waitForAll()
        }
        let count = await transport.refreshes
        XCTAssertEqual(count, 1)
        XCTAssertEqual(try vault.read()?.tokens.access_token, "fresh")
        XCTAssertEqual(try vault.read()?.rotationPending, false)
    }
    func testLostRefreshResponseNeverReplaysAfterRestart() async throws {
        var stored = Credentials(tokens: tokens()); stored.accessUntil = .distantPast
        let vault = MemoryCredentials(stored), transport = AuthTransport()
        await transport.timeout()
        let api = try API(base: URL(string: "https://api.example.com")!, transport: transport)
        for _ in 0..<2 {
            let session = Session(api: api, store: vault)
            do { _ = try await session.request("me"); XCTFail("ambiguous rotation must fail") }
            catch let failure as ClientError { XCTAssertTrue(["TIMEOUT", "ROTATION_UNCERTAIN"].contains(failure.code)) }
        }
        let count = await transport.refreshes
        XCTAssertEqual(count, 1)
        XCTAssertEqual(try vault.read()?.rotationPending, true)
    }
    func testExplicitUnauthorizedRefreshesAndRetriesOnce() async throws {
        let transport = AuthTransport(); await transport.reject()
        let session = Session(api: try API(base: URL(string: "https://api.example.com")!, transport: transport), store: MemoryCredentials(Credentials(tokens: tokens())))
        _ = try await session.request("me")
        let count = await transport.refreshes
        XCTAssertEqual(count, 1)
    }
    func testAPIRejectsHTTPAndCredentialURLs() throws {
        for raw in ["http://api.example.com", "https://user:secret@api.example.com", "https://api.example.com?token=x"] {
            XCTAssertThrowsError(try API(base: URL(string: raw)!))
        }
    }
    func testRevokedSessionCannotBecomeAuthenticated() async throws {
        let vault = MemoryCredentials()
        let session = Session(api: try API(base: URL(string: "https://api.example.com")!), store: vault)
        do { _ = try await session.request("me"); XCTFail("missing credentials") }
        catch let error as ClientError { XCTAssertEqual(error.code, "REAUTH_REQUIRED") }
    }
}
