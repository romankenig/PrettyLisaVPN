#if DEBUG && targetEnvironment(simulator)
import Foundation
import PrettyLisaCore

/// Exercise the shipping Keychain adapter inside the exact packaged Simulator app.
/// No account/session item, credential, network request or fixture authentication.
func verifySimulatorKeychain(_ vault: KeychainStore) throws {
    let account = "simulator-check-" + UUID().uuidString
    let value = Data("PrettyLisaVPN simulator storage check".utf8)
    defer { try? vault.delete(account) }
    try vault.save(value, account: account)
    guard try vault.data(account) == value else { throw ClientError("SECURE_STORAGE_UNAVAILABLE") }
    let updated = Data("updated".utf8)
    try vault.save(updated, account: account)
    guard try vault.data(account) == updated else { throw ClientError("SECURE_STORAGE_UNAVAILABLE") }
    try vault.delete(account)
    guard try vault.data(account) == nil else { throw ClientError("SECURE_STORAGE_UNAVAILABLE") }
    let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    let receipt = try JSONSerialization.data(withJSONObject: ["read_write_update_delete": true])
    try receipt.write(to: directory.appendingPathComponent("simulator-keychain-check.json"), options: .atomic)
}
#endif
