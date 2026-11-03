import SwiftUI
import CryptoKit
import PrettyLisaCore

@MainActor final class AppModel: ObservableObject {
    enum Page: String, CaseIterable, Identifiable {
        case home, subscription, devices, messages, support, settings, about
        var id: String { rawValue }
        var key: String { ["home": "home", "subscription": "ui_subscription", "devices": "ui_devices", "messages": "ui_account_messages", "support": "ui_help_and_support", "settings": "settings", "about": "about"][rawValue]! }
        var icon: String { ["home": "shield.lefthalf.filled", "subscription": "creditcard", "devices": "desktopcomputer.and.iphone", "messages": "envelope", "support": "questionmark.bubble", "settings": "gearshape", "about": "info.circle"][rawValue]! }
    }
    @Published var page: Page = .home
    @Published var profile: Profile?
    @Published var countries: Countries?
    @Published var devices: [Device] = []
    @Published var messages: [AccountMessage] = []
    @Published var billing: BillingOverview?
    @Published var backendVersion: String?
    @Published var error: String?
    @Published var busy = false
    @Published var otpSent = false
    @Published var needsSignIn = false
    @Published var country = "AUTO"
    @Published var methods = Methods.all
    @Published var supportReceipt: SupportReceipt?
    @Published var supportFrozen = false
    #if DEBUG && targetEnvironment(simulator)
    let simulator = SimulatorVPNController()
    #endif
    let session: Session
    let vpn: VPNCoordinator
    let vault: KeychainStore
    let platform: String
    let version: String
    let simulation: Bool
    let fixtures: Bool
    private var supportRequest: SupportReport?
    private var supportImages: [SupportImage] = []

    init() throws {
        guard let address = Bundle.main.object(forInfoDictionaryKey: "APIBaseURL") as? String,
              let url = URL(string: address) else { throw ClientError("INVALID_API_URL") }
        let api = try API(base: url)
        #if targetEnvironment(simulator)
        vault = KeychainStore(group: nil)
        #else
        guard let group = Bundle.main.object(forInfoDictionaryKey: "SharedKeychainGroup") as? String,
              !group.contains("$("), !group.isEmpty else { throw ClientError("SIGNING_REQUIRED") }
        vault = KeychainStore(group: group)
        #endif
        #if os(iOS)
        platform = "IOS"
        #else
        platform = "MACOS"
        #endif
        version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.1.0"
        session = Session(api: api, store: vault)
        let driver = NetworkTunnelDriver(store: vault, extensionID: (Bundle.main.bundleIdentifier ?? "") + ".tunnel")
        vpn = VPNCoordinator(session: session, driver: driver) {
            let key = Curve25519.KeyAgreement.PrivateKey()
            return (key.rawRepresentation.base64EncodedString(), key.publicKey.rawRepresentation.base64EncodedString())
        }
        #if DEBUG
        fixtures = ProcessInfo.processInfo.arguments.contains("-ui-fixtures")
        #if targetEnvironment(simulator)
        simulation = ProcessInfo.processInfo.arguments.contains("-simulate-vpn")
        #else
        simulation = false
        #endif
        #else
        fixtures = false; simulation = false
        #endif
        if let saved = UserDefaults.standard.stringArray(forKey: "methods"), !saved.isEmpty, saved.allSatisfy(Methods.all.contains) { methods = saved }
        vpn.onChange = { [weak self] in self?.objectWillChange.send() }
        vpn.onAuthorizationLost = { [weak self] in self?.error = "REAUTH_REQUIRED"; self?.needsSignIn = true }
        #if DEBUG && targetEnvironment(simulator)
        simulator.onChange = { [weak self] in self?.objectWillChange.send() }
        #endif
    }
    var controller: any VPNControlling {
        #if DEBUG && targetEnvironment(simulator)
        if simulation { return simulator }
        #endif
        return vpn
    }
    var connection: ConnectionState { controller.state }
    func perform(_ action: @escaping () async throws -> Void) {
        guard !busy else { return }
        busy = true; error = nil
        Task {
            defer { busy = false }
            do { try await action() }
            catch { self.handle(error) }
        }
    }
    private func handle(_ failure: Error) {
        let value = failure as? ClientError
        error = value?.code ?? "NETWORK_UNCERTAIN"
        if value?.terminal == true || value?.status == 401 { needsSignIn = true }
    }
    func restore() async {
        #if DEBUG
        if fixtures {
            do {
                profile = try fixture("profile", Profile.self)
                countries = try fixture("countries", Countries.self)
                devices = try fixture("devices", [Device].self)
                billing = try fixture("billing", BillingOverview.self)
            } catch { self.error = "INVALID_FIXTURE" }
            return
        }
        #endif
        do {
            backendVersion = try? WireJSON.decode(BackendVersion.self, from: await session.api.data("version")).application_version
            if try await session.hasCredentials() { try await refresh(); await vpn.reconcile() }
        } catch { handle(error) }
    }
    func requestOTP(_ email: String) {
        perform { try await self.session.requestOTP(email: email.trimmingCharacters(in: .whitespacesAndNewlines)); self.otpSent = true }
    }
    func login(email: String, code: String) {
        perform {
            // Stop the previous identity's tunnel before replacing credentials. A revoked/expired
            // session may prevent remote cleanup, but cannot justify keeping its local tunnel up.
            await self.vpn.disconnect()
            guard self.vpn.localTunnelDown else { throw ClientError("TUNNEL_STOP_FAILED") }
            try await self.session.login(email: email.trimmingCharacters(in: .whitespacesAndNewlines), code: code,
                                         installation: self.vault.installationID(), platform: self.platform, name: "PrettyLisaVPN " + self.platform)
            self.resetAccount()
            self.needsSignIn = false
            try await self.refresh(); await self.vpn.reconcile()
        }
    }
    func refresh() async throws {
        if fixtures { return }
        let current = try WireJSON.decode(Profile.self, from: await session.request("me"))
        guard ["FREE", "PREMIUM", "PLATINUM"].contains(current.plan), (0...5).contains(current.active_device_count) else { throw ClientError("INVALID_RESPONSE") }
        profile = current
        countries = try WireJSON.decode(Countries.self, from: await session.request("vpn/countries"))
        let context = [URLQueryItem(name: "platform", value: platform), .init(name: "app_version", value: version),
                       .init(name: "locale", value: Locale.current.identifier.replacingOccurrences(of: "_", with: "-")), .init(name: "schema_version", value: "1")]
        let inbox = try WireJSON.decode(Messages.self, from: await session.request("messages", query: context))
        guard inbox.schema_version == 1 else { throw ClientError("INVALID_RESPONSE") }
        messages = inbox.messages.filter { $0.expires_at.flatMap(WireJSON.date).map { $0 > Date() } ?? true }
    }
    func loadPage() async {
        guard profile != nil, !fixtures else { return }
        do {
            switch page {
            case .devices: devices = try WireJSON.decode([Device].self, from: await session.request("devices"))
            case .subscription: billing = try WireJSON.decode(BillingOverview.self, from: await session.request("billing/overview"))
            case .home: try await refresh(); await vpn.reconcile()
            default: break
            }
        } catch { handle(error) }
    }
    func connect() {
        if simulation {
            controller.connect(country: country, methods: methods)
            return
        }
        guard !fixtures else { error = "FIXTURE_NO_VPN"; return }
        #if targetEnvironment(simulator)
        error = "PHYSICAL_DEVICE_REQUIRED"
        #else
        vpn.connect(country: country, methods: methods)
        #endif
    }
    func disconnect() async {
        await controller.disconnect()
    }
    func logout() {
        perform {
            await self.disconnect()
            guard self.connection == .disconnected else { throw ClientError("CLEANUP_UNCONFIRMED") }
            try await self.session.logout(); self.resetAccount()
        }
    }
    func forget() {
        perform {
            // Explicit local reset never claims that server-side logout or quota release succeeded.
            await self.disconnect()
            try await self.session.forget(); self.resetAccount()
        }
    }
    private func resetAccount() {
        profile = nil; billing = nil; devices = []; messages = []; countries = nil
        supportRequest = nil; supportImages = []; supportReceipt = nil; supportFrozen = false
        otpSent = false; needsSignIn = false; page = .home
    }
    func revoke(_ device: Device) {
        perform {
            if device.is_current { await self.disconnect(); guard self.connection == .disconnected else { throw ClientError("CLEANUP_UNCONFIRMED") } }
            _ = try await self.session.request("devices/" + device.id.uuidString.lowercased(), method: "DELETE")
            if device.is_current { try await self.session.forget(); self.resetAccount() }
            else { await self.loadPage() }
        }
    }
    func acknowledge(_ message: AccountMessage, navigate: Bool = false) {
        perform {
            _ = try await self.session.request("messages/\(message.id.uuidString.lowercased())/acknowledgements", method: "POST", body: WireJSON.encode(["revision": message.revision]))
            self.messages.removeAll { $0.id == message.id }
            if navigate {
                self.page = ["OPEN_SUBSCRIPTION": Page.subscription, "OPEN_SETTINGS": .settings, "OPEN_ABOUT": .about][message.primary_action?.type ?? ""] ?? .messages
            }
        }
    }
    func submitSupport(subject: String, description: String, email: String, images: [SupportImage]) {
        guard !fixtures else { error = "FIXTURE_NO_VPN"; return }
        perform {
            if self.supportRequest == nil {
                let report = SupportReport(id: UUID(), subject: subject, description: description, email: email)
                _ = try report.multipart(images: images)
                let saved = SupportJournal(report: report, images: images)
                // Account-scoped journal survives lost responses and restarts; only its key is in Keychain.
                guard let account = self.profile?.id else { throw ClientError("REAUTH_REQUIRED") }
                try SupportJournalStore(vault: self.vault).save(WireJSON.encode(saved), account: account)
                self.supportRequest = report; self.supportImages = images; self.supportFrozen = true
            }
            try await self.sendSavedSupport()
        }
    }
    private var supportKey: String { "support-" + (profile?.id.uuidString ?? "signed-out") }
    private struct SupportJournal: Codable { let report: SupportReport; let images: [SupportImage] }
    func recoverSupport() async {
        guard let account = profile?.id, !fixtures else { return }
        do {
            if let data = try SupportJournalStore(vault: vault).read(account: account) {
                let saved = try WireJSON.decode(SupportJournal.self, from: data)
                supportRequest = saved.report; supportImages = saved.images; supportFrozen = true
            }
            try await supportStatus()
        } catch { self.error = (error as? ClientError)?.code ?? "NETWORK_UNCERTAIN" }
    }
    private func sendSavedSupport() async throws {
        guard let request = supportRequest else { return }
        let body = try request.multipart(images: supportImages)
        let receipt = try WireJSON.decode(SupportReceipt.self, from: await session.request("support/requests", method: "POST", body: body.body, headers: ["Content-Type": body.contentType]))
        try acceptSupport(receipt, expectedID: request.request_id)
    }
    private func acceptSupport(_ receipt: SupportReceipt, expectedID: UUID) throws {
        guard receipt.request_id == expectedID else { throw ClientError("INVALID_RESPONSE") }
        // Retain only the account-scoped identifier after acceptance, not attachments/content.
        try vault.save(WireJSON.encode(receipt), account: supportKey + "-receipt")
        if let account = profile?.id { try SupportJournalStore(vault: vault).remove(account: account) }
        supportReceipt = receipt; supportFrozen = true; supportImages = []; supportRequest = nil
    }
    func supportStatus() async throws {
        if supportReceipt == nil, let data = try vault.data(supportKey + "-receipt") { supportReceipt = try WireJSON.decode(SupportReceipt.self, from: data) }
        guard let id = supportRequest?.request_id ?? supportReceipt?.request_id else { return }
        do {
            let receipt = try WireJSON.decode(SupportReceipt.self, from: await session.request("support/requests/" + id.uuidString.lowercased()))
            try acceptSupport(receipt, expectedID: id)
        } catch let error as ClientError where error.code == "SUPPORT_NOT_FOUND" {
            if supportRequest != nil { try await sendSavedSupport() } else { throw error }
        }
    }
    func newSupport() {
        guard supportReceipt != nil else { return }
        supportRequest = nil; supportImages = []; supportReceipt = nil; supportFrozen = false
        if let account = profile?.id { try? SupportJournalStore(vault: vault).remove(account: account) }
        try? vault.delete(supportKey + "-receipt")
    }
    #if DEBUG
    private func fixture<T: Decodable>(_ name: String, _ type: T.Type) throws -> T {
        guard let url = Bundle.main.url(forResource: name, withExtension: "json", subdirectory: "Fixtures") else { throw ClientError("INVALID_FIXTURE") }
        return try WireJSON.decode(type, from: Data(contentsOf: url))
    }
    #endif
}

func L(_ key: String) -> String {
    let language = UserDefaults.standard.string(forKey: "language") ?? "system"
    let bundle = language == "system" ? Bundle.main : Bundle.main.path(forResource: language, ofType: "lproj").flatMap(Bundle.init(path:)) ?? .main
    return bundle.localizedString(forKey: key, value: nil, table: nil)
}
