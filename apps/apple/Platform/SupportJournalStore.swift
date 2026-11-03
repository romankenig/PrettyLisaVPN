import Foundation
import CryptoKit
import PrettyLisaCore

/// Attachments can exceed Keychain item limits. Only the encryption key goes in Keychain.
/// Names are account UUIDs; user filenames and browsing data are never persisted.
struct SupportJournalStore {
    let vault: KeychainStore
    private func file(_ account: UUID) throws -> URL {
        let directory = try FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                                     appropriateFor: nil, create: true)
            .appendingPathComponent("PrettyLisaVPN/Support", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        var protected = directory
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try protected.setResourceValues(values)
        return directory.appendingPathComponent(account.uuidString + ".sealed")
    }
    private func key() throws -> SymmetricKey {
        if let data = try vault.data("support-journal-key") {
            guard data.count == 32 else { throw ClientError("SECURE_STORAGE_UNAVAILABLE") }
            return SymmetricKey(data: data)
        }
        let key = SymmetricKey(size: .bits256)
        try vault.save(key.withUnsafeBytes { Data($0) }, account: "support-journal-key")
        return key
    }
    func save(_ data: Data, account: UUID) throws {
        guard data.count <= 15 * 1024 * 1024, let sealed = try AES.GCM.seal(data, using: key()).combined else { throw ClientError("INVALID_REQUEST") }
        let url = try file(account)
        try sealed.write(to: url, options: .atomic)
        #if os(iOS)
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: url.path)
        #endif
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    }
    func read(account: UUID) throws -> Data? {
        let url = try file(account)
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let info = try url.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
        guard (info.fileSize ?? Int.max) <= 15 * 1024 * 1024 else { throw ClientError("INVALID_RESPONSE") }
        if (info.contentModificationDate ?? .distantPast) < Date().addingTimeInterval(-30 * 86400) {
            try remove(account: account); return nil
        }
        return try AES.GCM.open(AES.GCM.SealedBox(combined: Data(contentsOf: url)), using: key())
    }
    func remove(account: UUID) throws {
        let url = try file(account)
        if FileManager.default.fileExists(atPath: url.path) { try FileManager.default.removeItem(at: url) }
    }
}
