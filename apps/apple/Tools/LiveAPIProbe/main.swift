import Foundation
import PrettyLisaCore

// Real, unauthenticated HTTPS smoke check through the same transport as the app.
// No OTP, credentials, lease allocation or VPN-success claim.
let address = ProcessInfo.processInfo.environment["APPLE_API_BASE_URL"] ?? "https://api.prettylisavpn.com"
guard let url = URL(string: address) else { throw ClientError("INVALID_API_URL") }
let api = try API(base: url)
let health = try WireJSON.decode([String: String].self, from: await api.data("health"))
guard health["status"] == "ok" else { throw ClientError("HEALTH_UNAVAILABLE") }
let version = try WireJSON.decode(BackendVersion.self, from: await api.data("version"))
do {
    _ = try await api.data("me")
    throw ClientError("AUTHENTICATION_FENCE_MISSING")
} catch let error as ClientError where error.status == 401 {
    print("Live HTTPS health/version/authentication fence passed. Backend: \(version.application_version)")
    print("Authenticated account flows and real VPN are not verified by this check.")
}
