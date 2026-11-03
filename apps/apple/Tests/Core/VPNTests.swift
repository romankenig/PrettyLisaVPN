import XCTest
@testable import PrettyLisaCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

@MainActor final class TestDriver: TunnelDriver {
    var status: DriverStatus = .down
    var leaseID: UUID?
    var onStatus: (() -> Void)?
    var starts = 0
    var stops = 0
    var traffic = true
    var reloadDelay: UInt64 = 0
    func reload() async throws { if reloadDelay > 0 { try await Task.sleep(nanoseconds: reloadDelay) } }
    func start(_ payload: TunnelPayload) async throws { starts += 1; status = .up; leaseID = payload.leaseID }
    func stop() async throws { stops += 1; status = .down }
    func hasTraffic() async throws -> Bool { traffic }
}
actor VPNTransport: HTTPTransport {
    var creates = 0
    var deletes = 0
    var closed = false
    var loseCreateResponse = false
    var wrongEgress = false
    func loseResponse() { loseCreateResponse = true }
    func rejectEgress() { wrongEgress = true }
    func send(_ request: URLRequest) async throws -> (Data, Int) {
        if request.url!.path.hasSuffix("/current") { return (creates > 0 && !closed ? try leaseData() : Data("null".utf8), 200) }
        if request.httpMethod == "POST" {
            creates += 1
            XCTAssertNotNil(request.value(forHTTPHeaderField: "Idempotency-Key"))
            let body = String(decoding: request.httpBody!, as: UTF8.self)
            XCTAssertFalse(body.contains("private_key"))
            if loseCreateResponse { throw ClientError("TIMEOUT") }
            return (try leaseData(), 202)
        }
        if request.httpMethod == "DELETE" { deletes += 1; closed = true }
        if request.url!.path.hasSuffix("/probe") {
            return (Data((wrongEgress ? #"{"verified":false,"ip":"1.2.3.4"}"# : #"{"verified":true,"ip":"8.8.4.4"}"#).utf8), 200)
        }
        if closed {
            var value = try JSONSerialization.jsonObject(with: leaseData()) as! [String: Any]
            value["status"] = "CLOSED"; value.removeValue(forKey: "configuration")
            return (try JSONSerialization.data(withJSONObject: value), 200)
        }
        return (try leaseData(), 200)
    }
}
final class VPNTests: XCTestCase {
    @MainActor func testDisconnectCancelsReconciliationAndBlocksConcurrentStart() async throws {
        let http = VPNTransport(), driver = TestDriver(); driver.reloadDelay = 1_000_000_000
        let session = Session(api: try API(base: URL(string: "https://api.example.com")!, transport: http), store: MemoryCredentials(Credentials(tokens: tokens())))
        let vpn = VPNCoordinator(session: session, driver: driver, keyPair: { (testKey, testKey) })
        let restore = Task { await vpn.reconcile() }
        for _ in 0..<100 { if vpn.busy { break }; try await Task.sleep(nanoseconds: 1_000_000) }
        vpn.connect(country: "DE", methods: ["wireguard"])
        await vpn.disconnect(); await restore.value
        XCTAssertEqual(vpn.state, .disconnected)
        XCTAssertFalse(vpn.busy)
        XCTAssertEqual(driver.starts, 0)
        let creates = await http.creates
        XCTAssertEqual(creates, 0)
    }
    @MainActor func testLostCreateResponseDiscoversAndRemovesPeerBeforeFailing() async throws {
        let http = VPNTransport(), driver = TestDriver(); await http.loseResponse()
        let session = Session(api: try API(base: URL(string: "https://api.example.com")!, transport: http), store: MemoryCredentials(Credentials(tokens: tokens())))
        let vpn = VPNCoordinator(session: session, driver: driver, keyPair: { (testKey, testKey) })
        vpn.connect(country: "DE", methods: ["wireguard"])
        for _ in 0..<100 { if !vpn.busy { break }; try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(vpn.state, .failed("TIMEOUT"))
        XCTAssertEqual(driver.starts, 0)
        let creates = await http.creates, deletes = await http.deletes
        XCTAssertEqual(creates, 1); XCTAssertEqual(deletes, 1)
    }
    @MainActor func testInterfaceUpWithWrongEgressNeverReportsConnected() async throws {
        let http = VPNTransport(), driver = TestDriver(); await http.rejectEgress()
        let session = Session(api: try API(base: URL(string: "https://api.example.com")!, transport: http), store: MemoryCredentials(Credentials(tokens: tokens())))
        let vpn = VPNCoordinator(session: session, driver: driver, keyPair: { (testKey, testKey) })
        vpn.connect(country: "DE", methods: ["wireguard"])
        for _ in 0..<100 { if driver.status == .up { break }; try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertFalse(vpn.state.protected)
        XCTAssertNil(vpn.verifiedIP)
        await vpn.disconnect()
        XCTAssertEqual(vpn.state, .disconnected)
        let deletes = await http.deletes
        XCTAssertEqual(deletes, 1)
    }
    @MainActor func testVerifiedConnectionSerializesDuplicatesAndConfirmsCleanup() async throws {
        let http = VPNTransport(), driver = TestDriver()
        let session = Session(api: try API(base: URL(string: "https://api.example.com")!, transport: http), store: MemoryCredentials(Credentials(tokens: tokens())))
        let vpn = VPNCoordinator(session: session, driver: driver, keyPair: { (testKey, testKey) })
        vpn.connect(country: "DE", methods: ["wireguard"])
        vpn.connect(country: "DE", methods: ["wireguard"])
        for _ in 0..<100 {
            if vpn.state.protected { break }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertEqual(vpn.state, .connected("wireguard"))
        XCTAssertEqual(vpn.verifiedIP, "8.8.4.4")
        XCTAssertEqual(driver.starts, 1)
        let creates = await http.creates
        XCTAssertEqual(creates, 1)
        await vpn.disconnect()
        XCTAssertEqual(vpn.state, .disconnected)
        XCTAssertNil(vpn.verifiedIP)
        let deletes = await http.deletes
        XCTAssertEqual(deletes, 1)
    }
    @MainActor func testOSReassertionImmediatelyRemovesConnectedClaim() async throws {
        let http = VPNTransport(), driver = TestDriver()
        let session = Session(api: try API(base: URL(string: "https://api.example.com")!, transport: http), store: MemoryCredentials(Credentials(tokens: tokens())))
        let vpn = VPNCoordinator(session: session, driver: driver, keyPair: { (testKey, testKey) })
        vpn.connect(country: "AUTO", methods: ["wireguard"])
        for _ in 0..<100 {
            if vpn.state.protected { break }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        driver.status = .reasserting; driver.onStatus?()
        XCTAssertEqual(vpn.state, .reconnecting)
        XCTAssertFalse(vpn.state.protected)
        XCTAssertNil(vpn.verifiedIP)
        await vpn.disconnect()
    }
}
