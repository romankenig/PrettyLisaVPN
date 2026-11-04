#if os(iOS)
import SwiftUI
import PrettyLisaCore

// The phone shell follows the shared Android reference; account and tunnel state
// still come from AppModel. macOS keeps its native sidebar and appearance.
private enum PhoneStyle {
    static let purple = Color(red: 95 / 255, green: 34 / 255, blue: 217 / 255)
    static let chrome = Color(red: 44 / 255, green: 1 / 255, blue: 109 / 255)
    static let card = Color(red: 228 / 255, green: 228 / 255, blue: 228 / 255)
    static let ink = Color(red: 1 / 255, green: 1 / 255, blue: 1 / 255)
    static let secondary = Color(red: 91 / 255, green: 91 / 255, blue: 91 / 255)
    static let mint = Color(red: 81 / 255, green: 214 / 255, blue: 202 / 255)
    static let lilac = Color(red: 172 / 255, green: 115 / 255, blue: 255 / 255)
    static let danger = Color(red: 200 / 255, green: 43 / 255, blue: 40 / 255)
    static func font(_ size: CGFloat = 16, _ weight: Font.Weight = .regular, relativeTo: Font.TextStyle = .body) -> Font {
        .custom("Rubik-Light", size: size, relativeTo: relativeTo).weight(weight)
    }
}

private struct PhoneCard<Content: View>: View {
    @ViewBuilder var content: () -> Content
    var body: some View {
        VStack(alignment: .leading, spacing: 18, content: content)
            .frame(maxWidth: .infinity, alignment: .leading).padding(20)
            .foregroundStyle(PhoneStyle.ink)
            .background(PhoneStyle.card, in: RoundedRectangle(cornerRadius: 18))
    }
}

private struct PhoneActionStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(PhoneStyle.font(17, .bold))
            .frame(maxWidth: .infinity, minHeight: 54).padding(.horizontal, 12)
            .foregroundStyle(PhoneStyle.ink)
            .background(PhoneStyle.mint, in: RoundedRectangle(cornerRadius: 13))
            .opacity(!enabled ? 0.45 : configuration.isPressed ? 0.75 : 1)
    }
}

struct IOSRootView<Banners: View>: View {
    @ObservedObject var model: AppModel
    let onLogout: () -> Void
    @ViewBuilder var banners: () -> Banners
    @AppStorage("language") private var language = "system"
    @State private var advanced = false
    private var signedIn: Bool { model.profile != nil && !model.needsSignIn }
    private var nested: Bool { advanced || ![.home, .settings, .about].contains(model.page) }
    private var selectedTab: AppModel.Page {
        switch model.page {
        case .subscription, .devices: return .settings
        case .support: return .about
        case .messages: return .home
        default: return model.page
        }
    }
    var body: some View {
        VStack(spacing: 0) {
            header
            banners().font(PhoneStyle.font(13))
            if signedIn {
                if nested { backButton }
                content.frame(maxWidth: .infinity, maxHeight: .infinity)
                    .id(advanced ? "advanced" : model.page.rawValue)
            } else {
                LoginView(model: model).foregroundStyle(PhoneStyle.ink)
                    .background(PhoneStyle.card)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            footer
        }
        .font(PhoneStyle.font()).tint(PhoneStyle.purple)
        .background(PhoneStyle.purple)
        .background(PhoneStyle.chrome.ignoresSafeArea())
        // The supplied reference uses fixed light cards in its purple shell in both OS themes.
        // System sheets/forms remain light too so their field contrast matches those cards.
        .environment(\.colorScheme, .light)
        .onChange(of: model.page) { _, _ in advanced = false }
    }
    private var header: some View {
        HStack(spacing: 10) {
            HStack(spacing: 8) {
                Image("BrandMark").resizable().renderingMode(.template).scaledToFit()
                    .frame(width: 34, height: 44).accessibilityHidden(true)
                Text("PrettyLisaVPN").font(PhoneStyle.font(20, .bold)).lineLimit(1).minimumScaleFactor(0.7)
            }.accessibilityElement(children: .combine).accessibilityIdentifier("header-brand")
            Spacer(minLength: 6)
            Menu {
                Picker(L("apple_language"), selection: $language) {
                    Text(L("apple_system")).tag("system")
                    ForEach(Self.languages, id: \.code) { item in Text(item.native).tag(item.code) }
                }
            } label: {
                HStack(spacing: 6) {
                    Text(selectedLanguage.flag)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(selectedLanguage.english)
                        Text(selectedLanguage.native).opacity(0.8)
                    }.font(PhoneStyle.font(10, .medium, relativeTo: .caption))
                }.padding(.vertical, 10)
            }.accessibilityLabel(L("apple_language")).accessibilityIdentifier("language-picker")
        }.foregroundStyle(PhoneStyle.card).padding(.horizontal, 20).padding(.vertical, 10)
            .background(PhoneStyle.chrome, ignoresSafeAreaEdges: .top)
    }
    private struct Language {
        let code: String; let english: String; let native: String; let flag: String
    }
    private static let languages = [
        Language(code: "en", english: "English", native: "English", flag: "🇬🇧"),
        Language(code: "ru", english: "Russian", native: "Русский", flag: "🇷🇺"),
        Language(code: "de", english: "German", native: "Deutsch", flag: "🇩🇪"),
        Language(code: "es", english: "Spanish", native: "Español", flag: "🇪🇸"),
        Language(code: "fr", english: "French", native: "Français", flag: "🇫🇷"),
        Language(code: "zh-Hans", english: "Chinese", native: "简体中文", flag: "🇨🇳")
    ]
    private var selectedLanguage: Language {
        let code = language == "system" ? Bundle.main.preferredLocalizations.first ?? "en" : language
        return Self.languages.first { $0.code == code } ?? Self.languages[0]
    }
    private var backButton: some View {
        HStack {
            Button {
                if advanced { advanced = false }
                else { model.page = selectedTab }
            } label: { Image(systemName: "arrow.left").font(.title2).frame(width: 44, height: 44) }
                .accessibilityLabel(L("ios_back")).accessibilityIdentifier("nav-back")
            Spacer()
        }.foregroundStyle(PhoneStyle.card).padding(.horizontal, 12).padding(.top, 8)
    }
    @ViewBuilder private var content: some View {
        if advanced {
            SettingsView(model: model).scrollContentBackground(.hidden)
        } else {
            switch model.page {
            case .home: IOSHomeView(model: model)
            case .settings: settings
            case .about: IOSAboutView(model: model)
            case .devices: IOSDevicesView(model: model)
            case .subscription: SubscriptionView(model: model).scrollContentBackground(.hidden)
            case .messages: MessagesView(model: model).scrollContentBackground(.hidden)
            case .support: SupportView(model: model).scrollContentBackground(.hidden)
            }
        }
    }
    private var settings: some View {
        PhonePage(title: L("settings")) {
            settingsRow("ui_subscription", detail: "ui_manage_your_plan_and_payments", icon: "creditcard", id: "settings-subscription") { model.page = .subscription }
            settingsRow("ui_devices", detail: "ui_manage_account_access", icon: "desktopcomputer", id: "settings-devices") { model.page = .devices }
            settingsRow("advanced_settings", detail: "apple_methods", icon: "gearshape", id: "settings-advanced") { advanced = true }
            settingsRow("ui_sign_out", detail: "dash_end_session", icon: "rectangle.portrait.and.arrow.right", id: "settings-logout", danger: true, action: onLogout)
                .disabled(model.busy)
        }
    }
    private func settingsRow(_ title: String, detail: String, icon: String, id: String, danger: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 16) {
                Image(systemName: icon).font(.system(size: 25)).frame(width: 28)
                VStack(alignment: .leading, spacing: 6) {
                    Text(L(title)).font(PhoneStyle.font(17, .bold))
                    Text(L(detail)).font(PhoneStyle.font(12)).fixedSize(horizontal: false, vertical: true)
                }.frame(maxWidth: .infinity, alignment: .leading)
                if !danger { Image(systemName: "arrow.right") }
            }.padding(20).frame(maxWidth: .infinity, minHeight: 74, alignment: .leading)
                .foregroundStyle(danger ? PhoneStyle.card : PhoneStyle.ink)
                .background(danger ? PhoneStyle.danger : PhoneStyle.card, in: RoundedRectangle(cornerRadius: 14))
        }.buttonStyle(.plain).accessibilityIdentifier(id)
    }
    private var footer: some View {
        VStack(alignment: .leading, spacing: 16) {
            if signedIn && !nested {
                HStack(alignment: .top, spacing: 4) {
                    tab(.home, icon: "house")
                    tab(.settings, icon: "gearshape")
                    tab(.about, icon: "info.circle")
                }
            }
            Text("frontend \(model.version) · backend \(model.backendVersion ?? L("unavailable"))")
                .font(PhoneStyle.font(10, .medium, relativeTo: .caption)).foregroundStyle(PhoneStyle.mint)
                .accessibilityIdentifier("component-versions")
        }.padding(.horizontal, 12).padding(.top, 12).padding(.bottom, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(PhoneStyle.chrome, ignoresSafeAreaEdges: .bottom)
    }
    private func tab(_ page: AppModel.Page, icon: String) -> some View {
        let selected = selectedTab == page
        return Button { advanced = false; model.page = page } label: {
            VStack(spacing: 6) {
                Image(systemName: icon).font(.system(size: 22, weight: .medium))
                    .frame(width: 50, height: 38)
                    .foregroundStyle(selected ? PhoneStyle.ink : PhoneStyle.card)
                    .background(selected ? PhoneStyle.mint : .clear, in: RoundedRectangle(cornerRadius: 13))
                Text(L(page.key)).font(PhoneStyle.font(11, .medium, relativeTo: .caption))
                    .foregroundStyle(selected ? PhoneStyle.mint : PhoneStyle.card)
            }.frame(maxWidth: .infinity).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityIdentifier("nav-" + page.rawValue)
            .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

private struct PhonePage<Content: View>: View {
    var title: String? = nil
    @ViewBuilder var content: () -> Content
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if let title { Text(title).font(PhoneStyle.font(29, .bold, relativeTo: .largeTitle)).foregroundStyle(PhoneStyle.card) }
                content()
            }.padding(20).frame(maxWidth: 720).frame(maxWidth: .infinity)
        }
    }
}

private struct IOSHomeView: View {
    @ObservedObject var model: AppModel
    @Environment(\.locale) private var locale
    @State private var policy = false
    private var canStart: Bool {
        switch model.connection {
        case .disconnected: return true
        case .failed: return model.simulation || model.vpn.localTunnelDown
        default: return false
        }
    }
    private var status: String { HomeView(model: model).stateKey }
    private var plan: String {
        switch model.profile?.plan { case "PLATINUM": return "Platinum 💎"; case "PREMIUM": return "Premium"; case "FREE": return "Free"; default: return L("unavailable") }
    }
    var body: some View {
        PhonePage {
            PhoneCard {
                field("dash_account", model.profile?.email ?? "")
                HStack(alignment: .top, spacing: 24) {
                    field("dash_plan", plan)
                    field("dash_devices", "\(model.profile?.active_device_count ?? 0) / 5")
                }
                if let seconds = model.profile?.entitlements?.remaining {
                    HStack {
                        Text(L("free_time_remaining"))
                        Spacer()
                        Text("\(max(0, seconds) / 60):" + String(format: "%02d", max(0, seconds) % 60)).monospacedDigit()
                    }.font(PhoneStyle.font(12)).foregroundStyle(PhoneStyle.secondary)
                }
            }.accessibilityIdentifier("account-card")
            PhoneCard {
                Text(L("dash_where")).font(PhoneStyle.font(18, .bold))
                Menu {
                    Picker(L("dash_where"), selection: $model.country) {
                        Text("🌐 " + L("ui_autopilot")).tag("AUTO")
                        ForEach(model.countries?.countries ?? []) { country in
                            Text(flag(country.country_code) + " " + countryName(country.country_code))
                                .tag(country.country_code).disabled(!country.available)
                        }
                    }
                } label: {
                    HStack {
                        Text(model.country == "AUTO" ? "🌐 " + L("ui_autopilot") : flag(model.country) + " " + countryName(model.country))
                        Spacer(); Image(systemName: "chevron.down").font(.caption)
                    }.padding(.horizontal, 22).frame(minHeight: 44)
                        .foregroundStyle(PhoneStyle.purple)
                        .overlay(Capsule().stroke(PhoneStyle.purple.opacity(0.4), lineWidth: 1.2))
                }.disabled(!canStart).accessibilityIdentifier("country-picker")
                if model.countries?.autopilot.available == false { Text(L("dash_no_countries")).font(PhoneStyle.font(12)).foregroundStyle(PhoneStyle.secondary) }
                Button(L(canStart ? "dash_connect" : "vpn_disconnect")) {
                    if canStart { model.connect() } else { Task { await model.disconnect() } }
                }.buttonStyle(PhoneActionStyle())
                    .disabled(canStart ? model.busy || model.vpn.busy || model.countries == nil : model.connection == .disconnecting)
                    .accessibilityIdentifier(canStart ? "connect" : "disconnect")
                Text(L(status)).font(PhoneStyle.font(18, .bold)).accessibilityIdentifier("vpn-status")
                    .accessibilityAddTraits(.updatesFrequently)
                if case .connecting(let method) = model.connection { Text(Methods.label(method)) }
                if case .connected(let method) = model.connection { Text(Methods.label(method)) }
                if case .failed(let code) = model.connection { Text(errorText(code)).foregroundStyle(PhoneStyle.danger).font(PhoneStyle.font(13)) }
                if model.connection.protected, !model.simulation, let lease = model.vpn.lease, let ip = model.vpn.verifiedIP {
                    Divider().overlay(PhoneStyle.secondary.opacity(0.3))
                    HStack(spacing: 10) {
                        Text(flag(lease.country))
                        VStack(alignment: .leading, spacing: 4) {
                            Text(L("dash_region") + ": " + countryName(lease.country))
                            Text("IP: " + ip).textSelection(.enabled)
                        }.font(PhoneStyle.font(12)).foregroundStyle(PhoneStyle.secondary)
                    }.accessibilityIdentifier("verified-egress")
                }
            }.accessibilityIdentifier("connection-card")
            PhoneCard {
                HStack(alignment: .firstTextBaseline) {
                    Text(L("ui_what_to_protect")).font(PhoneStyle.font(18, .bold))
                    Text(L("traffic_all_short")).font(PhoneStyle.font(18, .bold)).foregroundStyle(PhoneStyle.purple)
                    Spacer(minLength: 0)
                    Button { policy = true } label: { Image(systemName: "info.circle").frame(width: 28, height: 44) }
                        .accessibilityLabel(L("apple_network_policy")).accessibilityIdentifier("routing-policy")
                }
                Text(L("traffic_description_all")).font(PhoneStyle.font(12)).foregroundStyle(PhoneStyle.secondary)
            }
            if !model.messages.isEmpty {
                Button(L("ui_account_messages") + " (\(model.messages.count))") { model.page = .messages }
                    .buttonStyle(PhoneActionStyle())
            }
        }.refreshable { await model.loadPage() }
            .sheet(isPresented: $policy) {
                VStack(alignment: .leading, spacing: 20) {
                    Text(L("apple_network_policy")).font(.title2.bold())
                    Text(L("apple_full_tunnel"))
                    Button(L("ui_close")) { policy = false }.buttonStyle(PhoneActionStyle())
                }.padding(24).presentationDetents([.medium, .large])
            }
    }
    private func field(_ key: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(L(key)).font(PhoneStyle.font(12)).foregroundStyle(PhoneStyle.secondary)
            Text(value).font(PhoneStyle.font(17, .bold)).textSelection(.enabled)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
    private func countryName(_ code: String) -> String { locale.localizedString(forRegionCode: code) ?? code }
    private func flag(_ code: String) -> String {
        guard code.count == 2, code.unicodeScalars.allSatisfy({ (65...90).contains($0.value) }) else { return "🌐" }
        return String(String.UnicodeScalarView(code.unicodeScalars.compactMap { UnicodeScalar(127397 + $0.value) }))
    }
}

private struct IOSDevicesView: View {
    @ObservedObject var model: AppModel
    @State private var revoke: Device?
    var body: some View {
        PhonePage(title: L("ui_devices")) {
            if model.devices.isEmpty { Text(L("ui_no_devices_to_display")).foregroundStyle(PhoneStyle.card) }
            ForEach(model.devices) { device in
                PhoneCard {
                    Text(device.device_name).font(PhoneStyle.font(18, .bold))
                    if device.is_current {
                        Text(L("ui_current_device")).font(PhoneStyle.font(17, .bold)).padding(.horizontal, 14).padding(.vertical, 8)
                            .background(PhoneStyle.lilac, in: RoundedRectangle(cornerRadius: 10))
                    }
                    Text(device.status == "ACTIVE" ? L("ui_active") : L("ui_revoked"))
                        .font(PhoneStyle.font(12)).foregroundStyle(PhoneStyle.secondary)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("id").foregroundStyle(PhoneStyle.secondary)
                        Text(device.id.uuidString.lowercased()).font(.system(size: 11, design: .monospaced)).textSelection(.enabled)
                    }.font(PhoneStyle.font(12))
                    date("dash_added", device.created_at)
                    date("dash_last_login", device.last_login_at)
                    if device.status == "ACTIVE" {
                        Button(L("ui_revoke_access_26")) { revoke = device }.buttonStyle(PhoneActionStyle())
                            .disabled(model.busy || model.fixtures).accessibilityIdentifier("device-revoke")
                    }
                }
            }
        }.refreshable { await model.loadPage() }
            .confirmationDialog(L("ui_revoke_access"), isPresented: Binding(get: { revoke != nil }, set: { if !$0 { revoke = nil } }), titleVisibility: .visible) {
                if let device = revoke { Button(L("ui_yes_revoke"), role: .destructive) { model.revoke(device) } }
            } message: { Text(L("ui_this_device_will_lose_account_access_revoking_this_device_ends_it")) }
    }
    private func date(_ key: String, _ value: String?) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(L(key)).font(PhoneStyle.font(12)).foregroundStyle(PhoneStyle.secondary)
            Text(value.map(formatDate) ?? L("unavailable")).font(PhoneStyle.font(16, .bold))
        }
    }
}

private struct IOSAboutView: View {
    @ObservedObject var model: AppModel
    @State private var faq = true
    var body: some View {
        PhonePage(title: L("about")) {
            HStack(alignment: .top, spacing: 30) {
                version("frontend", model.version)
                version("backend", model.backendVersion ?? L("unavailable"))
            }.foregroundStyle(PhoneStyle.card)
            PhoneCard {
                Text("faq").font(PhoneStyle.font(18, .bold))
                DisclosureGroup(isExpanded: $faq) {
                    VStack(alignment: .leading, spacing: 24) {
                        Text(L("faq_connect_a").replacingOccurrences(of: "[", with: "").replacingOccurrences(of: "]", with: ""))
                            .fixedSize(horizontal: false, vertical: true).lineSpacing(5)
                        Button(L("home")) { model.page = .home }.font(PhoneStyle.font(16, .bold))
                    }.padding(.vertical, 16)
                } label: { Text(L("faq_connect_q")).font(PhoneStyle.font(16, .bold)).foregroundStyle(PhoneStyle.purple) }
                    .accessibilityIdentifier("faq-connect")
            }
            PhoneCard {
                Text(L("about_support_title")).font(PhoneStyle.font(18, .bold))
                Text(L("about_support_prompt")).font(PhoneStyle.font(12)).foregroundStyle(PhoneStyle.secondary)
                Button(L("about_contact_support")) { model.page = .support }.buttonStyle(PhoneActionStyle())
                    .accessibilityIdentifier("about-support")
            }
            Text("inspired by love of my life, Lisa").font(PhoneStyle.font(11)).foregroundStyle(PhoneStyle.card.opacity(0.8))
            DisclosureGroup(L("ios_legal")) {
                VStack(alignment: .leading, spacing: 16) {
                    Link("prettylisavpn.com", destination: URL(string: "https://prettylisavpn.com")!)
                    Text(L("apple_licenses"))
                    Text(L("apple_full_tunnel"))
                    Text("Rubik · SIL Open Font License 1.1")
                }.font(PhoneStyle.font(12)).padding(.top, 12)
            }.foregroundStyle(PhoneStyle.card).tint(PhoneStyle.card)
        }
    }
    private func version(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(PhoneStyle.font(12))
            Text(value).font(PhoneStyle.font(14)).textSelection(.enabled)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}
#endif
