import XCTest
@testable import PrettyLisaCore

let testKey = Data(repeating: 7, count: 32).base64EncodedString()
func leaseData(changes: [String: Any] = [:]) throws -> Data {
    var config: [String: Any] = ["address": "10.88.0.2/32", "server_public_key": testKey, "endpoint": "8.8.4.4:51820",
                               "dns": ["1.1.1.1", "9.9.9.9"], "allowed_ips": ["0.0.0.0/0", "::/0"],
                               "mtu": 1280, "persistent_keepalive": 25, "expected_egress_ips": ["8.8.4.4"]]
    config.merge(changes) { _, new in new }
    return try JSONSerialization.data(withJSONObject: ["id": "22222222-2222-4222-8222-222222222222", "status": "READY", "country": "DE", "method": "wireguard",
                                                        "expires_at": "2099-01-01T00:00:00Z", "heartbeat_seconds": 30, "heartbeat_required": false, "configuration": config])
}
final class ContractTests: XCTestCase {
    func testManagedProfilePreservesTLSAndTransportParameters() throws {
        let profile: [String: Any] = ["version": 1, "session": "22222222-2222-4222-8222-222222222222",
                                      "country": "DE", "method": "VLESS_TLS", "server": "8.8.4.4", "port": 443,
                                      "secret": "33333333-3333-4333-8333-333333333333", "server_name": "node.example.com",
                                      "certificate_pin": String(repeating: "ab", count: 32), "transport": "ws", "path": "/vpn"]
        var object = try JSONSerialization.jsonObject(with: leaseData(changes: ["engine_profile": profile])) as! [String: Any]
        object["method"] = "vless"
        let lease = try WireJSON.decode(Lease.self, from: JSONSerialization.data(withJSONObject: object))
        let payload = try TunnelPayload.make(lease: lease, privateKey: testKey, apiBase: URL(string: "https://api.example.com")!)
        let forwarded = try JSONSerialization.jsonObject(with: WireJSON.encode(payload.profile)) as! NSDictionary
        XCTAssertEqual(forwarded, profile as NSDictionary)
    }
    func testWireGuardPreservesAuthorizedPeerAndDNS() throws {
        let lease = try WireJSON.decode(Lease.self, from: leaseData())
        let payload = try TunnelPayload.make(lease: lease, privateKey: testKey, apiBase: URL(string: "https://api.example.com")!)
        XCTAssertEqual(payload.profile.public_key, testKey)
        XCTAssertEqual(payload.profile.address, "10.88.0.2/32")
        XCTAssertEqual(payload.profile.port, 51820)
        XCTAssertEqual(payload.dns, ["1.1.1.1", "9.9.9.9"])
        XCTAssertEqual(payload.expectedEgress, ["8.8.4.4"])
        XCTAssertEqual(payload.profile.method, "WIREGUARD")
    }
    func testMalformedRoutesKeysEndpointsAndDNSFailClosed() throws {
        let cases: [[String: Any]] = [
            ["allowed_ips": ["0.0.0.0/0"]], ["server_public_key": "private\n[Peer]"], ["endpoint": "evil.example:1"],
            ["endpoint": "8.8.4.4:65536"], ["dns": []], ["dns": ["1.1.1.1\nPrivateKey=x"]], ["mtu": 9000],
            ["address": "10.0.0.1/8"], ["expected_egress_ips": []], ["persistent_keepalive": 0]
        ]
        for changes in cases {
            let lease = try WireJSON.decode(Lease.self, from: leaseData(changes: changes))
            XCTAssertThrowsError(try TunnelPayload.make(lease: lease, privateKey: testKey, apiBase: URL(string: "https://api.example.com")!))
        }
    }
    func testExpiredLeaseCannotStart() throws {
        let lease = try WireJSON.decode(Lease.self, from: leaseData())
        XCTAssertThrowsError(try TunnelPayload.make(lease: lease, privateKey: testKey, apiBase: URL(string: "https://api.example.com")!, now: .distantFuture))
    }
    func testAllBackendMethodsAndRelayVariantsHaveAnAdapter() {
        XCTAssertEqual(Methods.all.count, 22)
        for method in Methods.all { XCTAssertNotNil(Methods.engineName(for: method)) }
        XCTAssertNil(Methods.engineName(for: "unknown"))
    }
    func testSupportMultipartNeverIncludesFilePathAndRequiresExplicitNullDiagnostics() throws {
        let report = SupportReport(id: UUID(), subject: "Connection", description: "Unable to connect", email: "owner@example.com")
        let body = try report.multipart(images: [SupportImage(data: Data([1, 2]), type: "image/png")])
        let text = String(decoding: body.body, as: UTF8.self)
        XCTAssertTrue(text.contains("\"diagnostics\":null"))
        XCTAssertTrue(text.contains("filename=\"screenshot-0\""))
        XCTAssertThrowsError(try report.multipart(images: [SupportImage(data: Data(), type: "text/html")]))
    }
}
