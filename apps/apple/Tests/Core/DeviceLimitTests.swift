import XCTest
@testable import PrettyLisaCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

private actor PendingTransport: HTTPTransport {
    var optedIn = false
    func send(_ request: URLRequest) async throws -> (Data, Int) {
        if request.url!.path == "/auth/verify-otp" {
            let body = try JSONSerialization.jsonObject(with: request.httpBody!) as! [String: Any]
            optedIn = body["allow_device_management"] as? Bool == true
            return (try WireJSON.encode(tokens()), 200)
        }
        if request.url!.path == "/devices" { return (Data("[]".utf8), 200) }
        return (Data(#"{"error":{"code":"device_limit_reached"}}"#.utf8), 403)
    }
}

final class DeviceLimitTests: XCTestCase {
    func testPendingResponseDoesNotClearCredentialsAndStillAllowsDevices() async throws {
        let vault = MemoryCredentials(), transport = PendingTransport()
        let session = Session(api: try API(base: URL(string: "https://api.example.com")!, transport: transport), store: vault)
        try await session.login(email: "fixture@example.com", code: "123456", installation: UUID(), platform: "IOS", name: "Fixture")
        let optedIn = await transport.optedIn
        XCTAssertTrue(optedIn)
        do { _ = try await session.request("billing/overview"); XCTFail("pending device must be restricted") }
        catch let failure as ClientError { XCTAssertEqual(failure.code, "device_limit_reached"); XCTAssertFalse(failure.terminal) }
        XCTAssertNotNil(try vault.read())
        let devices = try WireJSON.decode([Device].self, from: await session.request("devices"))
        XCTAssertTrue(devices.isEmpty)
        try await session.forget()
        XCTAssertNil(try vault.read())
    }
    func testFiveActiveDevicesAloneDoNotRestrictAnAdmittedInstallation() throws {
        let existing = Data(#"{"id":"11111111-1111-4111-8111-111111111111","email":"fixture@example.com","plan":"PLATINUM","active_device_count":5}"#.utf8)
        XCTAssertFalse(try WireJSON.decode(Profile.self, from: existing).deviceLimited)
        let pending = Data(#"{"id":"11111111-1111-4111-8111-111111111111","email":"fixture@example.com","plan":"PLATINUM","active_device_count":5,"device_limit_reached":true}"#.utf8)
        XCTAssertTrue(try WireJSON.decode(Profile.self, from: pending).deviceLimited)
    }
}
