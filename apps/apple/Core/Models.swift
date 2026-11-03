import Foundation

public enum WireJSON {
    public static func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        do { return try JSONDecoder().decode(type, from: data) }
        catch { throw ClientError("INVALID_RESPONSE") }
    }
    public static func encode<T: Encodable>(_ value: T) throws -> Data {
        try JSONEncoder().encode(value)
    }
    public static func date(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return fractional.date(from: value) ?? ISO8601DateFormatter().date(from: value)
    }
}

public struct ClientError: Error, Equatable, Sendable {
    public let code: String
    public let status: Int
    public init(_ code: String, status: Int = 0) {
        self.code = code; self.status = status
    }
    public var terminal: Bool {
        ["invalid_session", "invalid_refresh_token", "device_revoked", "user_blocked",
         "account_unavailable", "AUTH_INVALID", "authentication_required", "REAUTH_REQUIRED"].contains(code)
        && status != 401 || ["REAUTH_REQUIRED", "invalid_refresh_token", "ROTATION_UNCERTAIN"].contains(code)
    }
}

public struct Tokens: Codable, Sendable {
    public let access_token: String
    public let refresh_token: String
    public let session_id: UUID
    public let access_token_expires_in: Int
    public let refresh_token_expires_at: String
    public let token_type: String
    public func validate() throws {
        guard token_type == "bearer", !access_token.isEmpty, access_token.count <= 8192,
              !refresh_token.isEmpty, refresh_token.count <= 512,
              access_token_expires_in > 0, WireJSON.date(refresh_token_expires_at) != nil
        else { throw ClientError("INVALID_RESPONSE") }
    }
}

public struct Credentials: Codable, Sendable {
    public var tokens: Tokens
    public var accessUntil: Date
    public var rotationPending: Bool
    public init(tokens: Tokens, now: Date = Date()) {
        self.tokens = tokens
        accessUntil = now.addingTimeInterval(Double(min(tokens.access_token_expires_in, 86400) - 10))
        rotationPending = false
    }
}

public struct Profile: Codable, Sendable {
    public let id: UUID
    public let email: String
    public let plan: String
    public let active_device_count: Int
    public let entitlements: Entitlements?
}
public struct Entitlements: Codable, Sendable {
    public let free_seconds_usable: Int?
    public let free_seconds_remaining: Int?
    public let free_running_sessions: Int?
    public let free_quota_resets_at: String?
    public let daily_vpn_limit_seconds: Int?
    public var remaining: Int? { free_seconds_usable ?? free_seconds_remaining }
}
public struct Device: Codable, Identifiable, Sendable {
    public let id: UUID
    public let device_name: String
    public let platform: String
    public let status: String
    public let created_at: String
    public let last_login_at: String?
    public let is_current: Bool
}
public struct Country: Codable, Identifiable, Sendable {
    public let country_code: String
    public let quality: Int
    public let available: Bool
    public var id: String { country_code }
}
public struct Countries: Codable, Sendable {
    public struct Auto: Codable, Sendable { public let quality: Int; public let available: Bool }
    public let autopilot: Auto
    public let countries: [Country]
}
public struct BackendVersion: Codable, Sendable { public let application_version: String }
public struct Probe: Codable, Sendable { public let verified: Bool; public let ip: String }
public enum LeaseStatus: String, Codable, Sendable { case PROVISIONING, READY, REVOKING, CLOSED }
public struct Lease: Codable, Sendable {
    public let id: UUID
    public let status: LeaseStatus
    public let country: String
    public let method: String
    public let code: String?
    public let expires_at: String
    public let heartbeat_seconds: Int
    public let heartbeat_required: Bool?
    public let configuration: VPNConfiguration?
    public var deadline: Date? { WireJSON.date(expires_at) }
}
public struct VPNConfiguration: Codable, Sendable {
    public let address: String?
    public let server_public_key: String?
    public let endpoint: String?
    public let dns: [String]?
    public let allowed_ips: [String]?
    public let mtu: Int?
    public let persistent_keepalive: Int?
    public let expected_egress_ips: [String]
    public let engine_profile: EngineProfile?
}
public struct EngineProfile: Codable, Sendable {
    public var version: Int
    public var session: String
    public var country: String
    public var method: String
    public var server: String
    public var port: Int
    public var secret: String
    public var server_name: String?
    public var public_key: String?
    public var short_id: String?
    public var obfs_secret: String?
    public var address: String?
    public var certificate_pin: String?
}
public struct TunnelPayload: Codable, Sendable {
    public let leaseID: UUID
    public let expiresAt: Date
    public let profile: EngineProfile
    public let dns: [String]
    public let expectedEgress: [String]
    public let apiBase: URL

    public static func make(lease: Lease, privateKey: String, apiBase: URL, now: Date = Date()) throws -> Self {
        guard lease.status == .READY, let deadline = lease.deadline, deadline > now,
              let config = lease.configuration, !config.expected_egress_ips.isEmpty,
              config.expected_egress_ips.allSatisfy(isIPv4),
              lease.heartbeat_required == false
        else { throw ClientError("UNSUPPORTED_CONFIGURATION") }
        let profile: EngineProfile
        let dns: [String]
        if let managed = config.engine_profile {
            guard managed.version == 1, managed.session == lease.id.uuidString.lowercased(),
                  managed.country == lease.country, isIPv4(managed.server), (1...65535).contains(managed.port),
                  Methods.engineName(for: lease.method) == managed.method, !managed.secret.isEmpty
            else { throw ClientError("UNSUPPORTED_CONFIGURATION") }
            profile = managed
            // The existing managed-engine contract uses these DNS settings, not an invented API field.
            dns = ["1.1.1.1"]
        } else {
            guard ["wireguard", "wireguard_relay"].contains(lease.method),
                  let address = config.address, address.hasSuffix("/32"), isIPv4(String(address.dropLast(3))),
                  let key = config.server_public_key, validKey(key), validKey(privateKey),
                  let endpoint = config.endpoint, let separator = endpoint.lastIndex(of: ":"),
                  let port = Int(endpoint[endpoint.index(after: separator)...]), (1...65535).contains(port),
                  isIPv4(String(endpoint[..<separator])),
                  config.allowed_ips == ["0.0.0.0/0", "::/0"],
                  let mtu = config.mtu, (1280...1420).contains(mtu), config.persistent_keepalive == 25,
                  let servers = config.dns, !servers.isEmpty, servers.allSatisfy(isIPv4)
            else { throw ClientError("UNSUPPORTED_CONFIGURATION") }
            profile = EngineProfile(version: 1, session: lease.id.uuidString.lowercased(), country: lease.country,
                                    method: "WIREGUARD", server: String(endpoint[..<separator]), port: port,
                                    secret: privateKey, public_key: key, address: address)
            dns = servers
        }
        return Self(leaseID: lease.id, expiresAt: deadline, profile: profile, dns: dns,
                    expectedEgress: config.expected_egress_ips, apiBase: apiBase)
    }
    public static func validKey(_ text: String) -> Bool {
        guard let data = Data(base64Encoded: text), data.count == 32 else { return false }
        return data.contains { $0 != 0 } && data.base64EncodedString() == text
    }
    public static func isIPv4(_ text: String) -> Bool {
        let parts = text.split(separator: ".", omittingEmptySubsequences: false)
        return parts.count == 4 && parts.allSatisfy { part in
            guard let n = UInt8(part) else { return false }; return String(n) == part
        }
    }
}

public enum Methods {
    public static let families = ["wireguard", "amneziawg", "sstp", "softether", "shadowsocks2022",
                                  "vmess", "vless", "vless_reality", "hysteria", "hysteria2", "hysteria2_salamander"]
    public static let all = families.flatMap { [$0, $0 + "_relay"] }
    public static func engineName(for method: String) -> String? {
        let base = method.hasSuffix("_relay") ? String(method.dropLast(6)) : method
        return ["wireguard": "WIREGUARD", "amneziawg": "AMNEZIA", "sstp": "SSTP", "softether": "SOFTETHER",
                "shadowsocks2022": "SHADOWSOCKS_2022", "vmess": "VMESS_TLS", "vless": "VLESS_TLS",
                "vless_reality": "VLESS_REALITY", "hysteria": "HYSTERIA1_TLS", "hysteria2": "HYSTERIA2_TLS",
                "hysteria2_salamander": "HYSTERIA2_SALAMANDER"][base]
    }
}
