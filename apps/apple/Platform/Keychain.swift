import Foundation
import Security
import PrettyLisaCore

struct KeychainStore: CredentialStore {
    let group: String?
    private var service: String { "com.prettylisavpn.apple" }
    private func query(_ account: String) -> [String: Any] {
        var value: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                    kSecAttrService as String: service, kSecAttrAccount as String: account,
                                    kSecUseDataProtectionKeychain as String: true]
        if let group { value[kSecAttrAccessGroup as String] = group }
        return value
    }
    func data(_ account: String) throws -> Data? {
        var q = query(account); q[kSecReturnData as String] = true
        var result: CFTypeRef?
        let status = SecItemCopyMatching(q as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else { throw ClientError("SECURE_STORAGE_UNAVAILABLE") }
        return data
    }
    func save(_ data: Data, account: String) throws {
        let q = query(account)
        let values: [String: Any] = [kSecValueData as String: data,
                                    kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        let updated = SecItemUpdate(q as CFDictionary, values as CFDictionary)
        if updated == errSecItemNotFound {
            guard SecItemAdd(q.merging(values) { _, new in new } as CFDictionary, nil) == errSecSuccess else {
                throw ClientError("SECURE_STORAGE_UNAVAILABLE")
            }
        } else if updated != errSecSuccess { throw ClientError("SECURE_STORAGE_UNAVAILABLE") }
    }
    func delete(_ account: String) throws {
        let status = SecItemDelete(query(account) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw ClientError("SECURE_STORAGE_UNAVAILABLE") }
    }
    func persistentReference(_ account: String) throws -> Data {
        var q = query(account); q[kSecReturnPersistentRef as String] = true
        var result: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &result) == errSecSuccess,
              let reference = result as? Data else { throw ClientError("SECURE_STORAGE_UNAVAILABLE") }
        return reference
    }
    static func resolve(_ reference: Data) throws -> Data {
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                               kSecValuePersistentRef as String: reference, kSecReturnData as String: true,
                               kSecUseDataProtectionKeychain as String: true]
        var result: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else { throw ClientError("SECURE_STORAGE_UNAVAILABLE") }
        return data
    }
    func read() throws -> Credentials? { try data("session").map { try WireJSON.decode(Credentials.self, from: $0) } }
    func write(_ credentials: Credentials) throws { try save(WireJSON.encode(credentials), account: "session") }
    func clear() throws { try delete("session") }
    func installationID() throws -> UUID {
        if let data = try data("installation"), let value = String(data: data, encoding: .utf8), let id = UUID(uuidString: value) { return id }
        let id = UUID(); try save(Data(id.uuidString.utf8), account: "installation"); return id
    }
}
