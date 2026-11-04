import SwiftUI
import UniformTypeIdentifiers
import PrettyLisaCore

struct RootView: View {
    @ObservedObject var model: AppModel
    @Environment(\.scenePhase) private var phase
    @Environment(\.colorScheme) private var colors
    @AppStorage("language") private var language = "system"
    @State private var logout = false
    var body: some View {
        VStack(spacing: 0) {
            banners
            if model.profile == nil || model.needsSignIn { LoginView(model: model) }
            else {
                NavigationSplitView {
                    List(AppModel.Page.allCases, selection: Binding<AppModel.Page?>(get: { model.page }, set: { model.page = $0 ?? .home })) { page in
                        NavigationLink(value: page) { Label(L(page.key), systemImage: page.icon) }
                            .accessibilityIdentifier("nav-" + page.rawValue)
                    }
                    .navigationTitle("PrettyLisaVPN")
                    .safeAreaInset(edge: .bottom) {
                        Button(role: .destructive) { logout = true } label: { Label(L("ui_sign_out"), systemImage: "rectangle.portrait.and.arrow.right") }
                            .padding()
                    }
                    .navigationSplitViewColumnWidth(min: 200, ideal: 230, max: 300)
                } detail: {
                    pageContent.navigationTitle(L(model.page.key))
                        .toolbar { Button { Task { await model.loadPage() } } label: { Label(L("ui_refresh"), systemImage: "arrow.clockwise") }.disabled(model.busy) }
                }
            }
        }
        .tint(colors == .dark ? Color(red: 0.675, green: 0.451, blue: 1) : Color(red: 0.373, green: 0.133, blue: 0.851))
        .environment(\.locale, language == "system" ? .current : Locale(identifier: language))
        .task { await model.restore() }
        .task(id: model.page) { await model.loadPage() }
        .task(id: phase) {
            guard phase == .active else { return }
            if model.profile != nil { await model.loadPage() }
            while !Task.isCancelled {
                do { try await Task.sleep(nanoseconds: 20_000_000_000) } catch { return }
                if model.profile != nil && !model.fixtures && !model.simulation { await model.vpn.reconcile() }
            }
        }
        .confirmationDialog(L("ui_sign_out_54"), isPresented: $logout, titleVisibility: .visible) {
            Button(L("ui_sign_out"), role: .destructive) { model.logout() }
        } message: { Text(L("ui_end_this_server_session_on_this_device_if_the_network_is_unavaila")) }
    }
    var banners: some View {
        VStack(spacing: 0) {
            if model.simulation { Text(L("apple_simulation")).font(.callout.bold()).frame(maxWidth: .infinity).padding(10).background(Color(red: 0.843, green: 0.678, blue: 0.051), ignoresSafeAreaEdges: []).foregroundStyle(.black).accessibilityIdentifier("simulation-banner") }
            if model.fixtures { Text(L("test_data_notice")).font(.callout.bold()).frame(maxWidth: .infinity).padding(8).background(Color(red: 0.894, green: 0.894, blue: 0.894), ignoresSafeAreaEdges: []).foregroundStyle(.black) }
            if let error = model.error { ErrorBanner(code: error) { model.error = nil } }
            if model.busy { ProgressView().frame(maxWidth: .infinity).padding(6).accessibilityLabel(L("processing")) }
        }
    }
    @ViewBuilder var pageContent: some View {
        switch model.page {
        case .home: HomeView(model: model)
        case .devices: DevicesView(model: model)
        case .subscription: SubscriptionView(model: model)
        case .messages: MessagesView(model: model)
        case .support: SupportView(model: model)
        case .settings: SettingsView(model: model)
        case .about: AboutView(model: model)
        }
    }
}

struct Logo: View {
    var body: some View {
        Image("Logo").resizable().renderingMode(.template).scaledToFit()
            .frame(maxWidth: 300, maxHeight: 150).accessibilityLabel("PrettyLisaVPN")
    }
}

struct LoginView: View {
    @ObservedObject var model: AppModel
    @State private var email = ""
    @State private var code = ""
    @State private var forget = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                Logo().frame(maxWidth: .infinity)
                Text(L("ui_sign_in_by_email")).font(.largeTitle.bold())
                Text(L(model.otpSent ? "ui_enter_the_code" : "ui_we_will_email_you_a_one_time_sign_in_code")).foregroundStyle(.secondary)
                TextField(L("ui_email"), text: $email).textFieldStyle(.roundedBorder).accessibilityIdentifier("email")
                    #if os(iOS)
                    .keyboardType(.emailAddress).textContentType(.emailAddress).textInputAutocapitalization(.never).autocorrectionDisabled()
                    #endif
                if model.otpSent {
                    TextField(L("ui_6_digit_code"), text: $code).textFieldStyle(.roundedBorder).accessibilityIdentifier("otp")
                        #if os(iOS)
                        .keyboardType(.numberPad).textContentType(.oneTimeCode)
                        #endif
                    Button(L("ui_sign_in")) { model.login(email: email, code: code) }
                        .buttonStyle(.borderedProminent).disabled(model.busy || code.count != 6).keyboardShortcut(.defaultAction)
                    Button(L("ui_change_email")) { model.otpSent = false; code = "" }
                } else {
                    Button(L("ui_continue")) { model.requestOTP(email) }.buttonStyle(.borderedProminent)
                        .disabled(model.busy || !email.contains("@") || email.count > 254).keyboardShortcut(.defaultAction)
                }
                if model.error != nil {
                    Button(L("ui_sign_in_again")) { forget = true }
                }
                if model.vpn.state != .disconnected {
                    Button(L("vpn_disconnect")) { Task { await model.disconnect() } }
                }
                Text("PrettyLisaVPN").font(.caption).foregroundStyle(.secondary)
            }.padding(28).frame(maxWidth: 480)
        }
        .confirmationDialog(L("ui_remove_local_session"), isPresented: $forget, titleVisibility: .visible) {
            Button(L("ui_remove_and_sign_in"), role: .destructive) { model.forget() }
        } message: { Text(L("ui_this_removes_local_credentials_and_opens_sign_in_it_does_not_conf")) }
    }
}

struct HomeView: View {
    @ObservedObject var model: AppModel
    @Environment(\.locale) private var locale
    var stateKey: String {
        switch model.connection {
        case .disconnected: return "ui_not_connected"
        case .connecting: return "vpn_connecting"
        case .verifying: return "apple_verifying"
        case .connected: return model.simulation ? "ui_simulated_connection" : "vpn_connected"
        case .reconnecting: return "apple_reconnecting"
        case .disconnecting: return "vpn_disconnecting"
        case .failed: return "vpn_failed"
        }
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Logo().frame(maxWidth: .infinity)
                GroupBox {
                    VStack(spacing: 16) {
                        Image(systemName: model.connection.protected && !model.simulation ? "checkmark.shield.fill" : "shield.slash")
                            .font(.system(size: 52)).foregroundStyle(model.connection.protected && !model.simulation ? Color.teal : Color.secondary)
                        Text(L(stateKey)).font(.title2.bold()).accessibilityIdentifier("vpn-status")
                        if case .connecting(let method) = model.connection { Text(Methods.label(method)).font(.callout).foregroundStyle(.secondary) }
                        if case .connected(let method) = model.connection { Text(Methods.label(method)).font(.callout).foregroundStyle(.secondary) }
                        if case .failed(let code) = model.connection { Text(errorText(code)).foregroundStyle(.red).font(.callout) }
                        if let ip = model.vpn.verifiedIP, !model.simulation { Text(ip).font(.body.monospaced()).textSelection(.enabled) }
                        HStack {
                            Button(L("dash_connect")) { model.connect() }.buttonStyle(.borderedProminent)
                                .disabled(model.busy || model.vpn.busy || model.connection.protected || model.countries == nil)
                                .accessibilityIdentifier("connect")
                            Button(L("vpn_disconnect")) { Task { await model.disconnect() } }.buttonStyle(.bordered)
                                .disabled(model.connection == .disconnected)
                                .accessibilityIdentifier("disconnect")
                        }.controlSize(.large)
                    }.padding().frame(maxWidth: .infinity)
                }
                GroupBox(L("dash_where")) {
                    Picker(L("dash_where"), selection: $model.country) {
                        Text(L("ui_autopilot")).tag("AUTO")
                        ForEach(model.countries?.countries ?? []) { country in
                            Text((locale.localizedString(forRegionCode: country.country_code) ?? country.country_code) + " · \(country.quality)%")
                                .tag(country.country_code).disabled(!country.available)
                        }
                    }.disabled(model.connection != .disconnected && !isFailed).padding(8)
                    if model.countries?.autopilot.available == false { Text(L("dash_no_countries")).foregroundStyle(.secondary) }
                }
                GroupBox(L("dash_account")) {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(model.profile?.email ?? "").textSelection(.enabled)
                        LabeledContent(L("dash_plan"), value: model.profile?.plan ?? L("unavailable"))
                        LabeledContent(L("dash_devices"), value: "\(model.profile?.active_device_count ?? 0) / 5")
                        if let quota = model.profile?.entitlements, let seconds = quota.remaining {
                            LabeledContent(L("free_time_remaining"), value: "\(max(0, seconds) / 60):" + String(format: "%02d", max(0, seconds) % 60))
                            if let reset = quota.free_quota_resets_at { Text(formatDate(reset)).font(.caption).foregroundStyle(.secondary) }
                        }
                    }.padding(8)
                }
                if !model.messages.isEmpty { Button(L("ui_account_messages") + " (\(model.messages.count))") { model.page = .messages } }
                Text(L("apple_full_tunnel")).font(.footnote).foregroundStyle(.secondary)
            }.padding().frame(maxWidth: 760).frame(maxWidth: .infinity)
        }
    }
    var isFailed: Bool { if case .failed = model.connection { return true }; return false }
}

struct DevicesView: View {
    @ObservedObject var model: AppModel
    @State private var revoke: Device?
    var body: some View {
        List {
            if model.devices.isEmpty { Text(L("ui_no_devices_to_display")).foregroundStyle(.secondary) }
            ForEach(model.devices) { device in
                VStack(alignment: .leading, spacing: 8) {
                    Label(device.device_name, systemImage: device.platform == "IOS" ? "iphone" : "desktopcomputer").font(.headline)
                    if device.is_current { Text(L("ui_current_device")).foregroundStyle(.secondary) }
                    Text(device.id.uuidString).font(.caption.monospaced()).textSelection(.enabled)
                    LabeledContent(L("dash_added"), value: formatDate(device.created_at))
                    LabeledContent(L("dash_last_login"), value: device.last_login_at.map(formatDate) ?? L("unavailable"))
                    if device.status == "ACTIVE" { Button(L("dash_end_session"), role: .destructive) { revoke = device }.disabled(model.busy || model.fixtures) }
                    else { Text(device.status).foregroundStyle(.secondary) }
                }.padding(.vertical, 8)
            }
        }
        .confirmationDialog(L("dash_end_session"), isPresented: Binding(get: { revoke != nil }, set: { if !$0 { revoke = nil } }), titleVisibility: .visible) {
            if let device = revoke { Button(L("ui_confirm"), role: .destructive) { model.revoke(device) } }
        } message: { Text(L("ui_this_device_will_lose_account_access_revoking_this_device_ends_it")) }
    }
}

struct SubscriptionView: View {
    @ObservedObject var model: AppModel
    var body: some View {
        Form {
            if let billing = model.billing {
                Section(L("ui_subscription")) {
                    LabeledContent(L("dash_plan"), value: billing.plan)
                    LabeledContent(L("apple_status"), value: billing.status)
                    LabeledContent(L("apple_paid_until"), value: billing.paid_until.map(formatDate) ?? L("ui_no_paid_period"))
                    LabeledContent(L("apple_auto_renew"), value: L(billing.auto_renew ? "ui_on" : "ui_off"))
                    if let price = billing.current_price { LabeledContent(L("apple_contract_price"), value: money(price.amount_minor, price.currency ?? "")) }
                    if billing.plan == "PLATINUM" { Text(L("ui_manually_assigned_premium_capabilities_no_purchase_needed")) }
                }
                Section("Premium") {
                    ForEach(billing.offers) { offer in
                        ForEach(offer.prices.keys.sorted(), id: \.self) { currency in
                            if let price = offer.prices[currency] { LabeledContent(currency, value: money(price.amount_minor, currency)) }
                        }
                    }
                    Text(L("apple_billing_readonly")).foregroundStyle(.secondary)
                }
            } else { Text(L("unavailable")) }
        }.formStyle(.grouped)
    }
}

struct MessagesView: View {
    @ObservedObject var model: AppModel
    var body: some View {
        List {
            if model.messages.isEmpty { Text(L("apple_no_messages")).foregroundStyle(.secondary) }
            ForEach(model.messages) { message in
                VStack(alignment: .leading, spacing: 14) {
                    Text(message.title).font(.headline)
                    Text(message.body).textSelection(.enabled)
                    if let action = message.primary_action { Button(action.label) { model.acknowledge(message, navigate: true) } }
                    Button(message.dismiss_label) { model.acknowledge(message) }
                }.padding(.vertical, 12).disabled(model.busy)
            }
        }
    }
}

struct SupportView: View {
    @ObservedObject var model: AppModel
    @State private var subject = ""
    @State private var description = ""
    @State private var email = ""
    @State private var images: [SupportImage] = []
    @State private var importing = false
    var body: some View {
        Form {
            Section {
                Text(L("ui_send_a_message_to_prettylisavpn_support_only_your_text_reply_addr"))
                TextField(L("subject"), text: $subject)
                TextField(L("reply_email"), text: $email)
                TextEditor(text: $description).frame(minHeight: 150).accessibilityLabel(L("description"))
                Text("\(description.count) / 4000").font(.caption).foregroundStyle(.secondary)
                Button(L("ui_attach_screenshots")) { importing = true }.disabled(images.count >= 3)
                ForEach(images.indices, id: \.self) { index in
                    HStack { Text("\(index + 1) · \(images[index].data.count / 1024) KB"); Spacer(); Button(L("dash_remove_image"), role: .destructive) { images.remove(at: index) } }
                }
                Button(L("ui_send_to_support")) { model.submitSupport(subject: subject, description: description, email: email, images: images) }
                    .disabled(subject.trimmingCharacters(in: .whitespaces).isEmpty || subject.count > 120 || description.isEmpty || description.count > 4000 || !email.contains("@"))
            }.disabled(model.busy || model.supportFrozen)
            if model.supportFrozen {
                Section {
                    if let receipt = model.supportReceipt {
                        Text(receipt.status).font(.headline)
                        Text(receipt.request_id.uuidString).font(.caption.monospaced()).textSelection(.enabled)
                        Text(L("ui_a_delivery_is_not_confirmed_until_the_server_reports_sent")).foregroundStyle(.secondary)
                        Button(L("ui_new_request")) { model.newSupport(); subject = ""; description = ""; images = [] }
                    } else { Text(L("ui_not_yet_confirmed")) }
                    Button(L("ui_check_status")) { model.perform { try await model.supportStatus() } }.disabled(model.busy)
                }
            }
        }.formStyle(.grouped)
        .task { email = model.profile?.email ?? ""; await model.recoverSupport() }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.png, .jpeg, .webP], allowsMultipleSelection: true) { result in
            do {
                let urls = try result.get()
                guard urls.count + images.count <= 3 else { throw ClientError("ATTACHMENT_REJECTED") }
                var loaded: [SupportImage] = []
                for url in urls {
                    let access = url.startAccessingSecurityScopedResource()
                    defer { if access { url.stopAccessingSecurityScopedResource() } }
                    let info = try url.resourceValues(forKeys: [.fileSizeKey, .contentTypeKey])
                    guard (info.fileSize ?? Int.max) <= 5 * 1024 * 1024,
                          let type = info.contentType?.preferredMIMEType else { throw ClientError("ATTACHMENT_REJECTED") }
                    loaded.append(SupportImage(data: try Data(contentsOf: url), type: type))
                }
                guard (images + loaded).reduce(0, { $0 + $1.data.count }) <= 10 * 1024 * 1024 else { throw ClientError("ATTACHMENT_REJECTED") }
                images += loaded
            } catch { model.error = "ATTACHMENT_REJECTED" }
        }
    }
}

struct SettingsView: View {
    @ObservedObject var model: AppModel
    @AppStorage("theme") private var theme = "system"
    @AppStorage("language") private var language = "system"
    var body: some View {
        Form {
            Section(L("apple_appearance")) {
                Picker(L("apple_theme"), selection: $theme) {
                    Text(L("apple_system")).tag("system"); Text(L("apple_light")).tag("light"); Text(L("apple_dark")).tag("dark")
                }
                Picker(L("apple_language"), selection: $language) {
                    Text(L("apple_system")).tag("system")
                    Text("English").tag("en"); Text("Русский").tag("ru"); Text("Deutsch").tag("de")
                    Text("Español").tag("es"); Text("Français").tag("fr"); Text("简体中文").tag("zh-Hans")
                }
            }
            Section(L("apple_methods")) {
                Text(L("apple_methods_detail")).font(.footnote).foregroundStyle(.secondary)
                ForEach(Methods.all, id: \.self) { method in
                    Toggle(Methods.label(method), isOn: Binding(get: { model.methods.contains(method) }, set: { enabled in
                        var selected = Set(model.methods)
                        if enabled { selected.insert(method) } else if selected.count > 1 { selected.remove(method) }
                        model.methods = Methods.all.filter(selected.contains)
                        UserDefaults.standard.set(model.methods, forKey: "methods")
                    }))
                }
            }.disabled(model.connection != .disconnected)
            #if DEBUG && targetEnvironment(simulator)
            if model.simulation {
                Section(L("apple_simulation")) {
                    Button("Disconnected") { model.simulator.select(.disconnected) }
                    Button("Connecting") { model.simulator.select(.connecting("WireGuard")) }
                    Button("Connected (simulation)") { model.simulator.select(.connected("WireGuard")) }
                    Button("Disconnecting") { model.simulator.select(.disconnecting) }
                    Button("Error") { model.simulator.select(.failed("SIMULATED_ERROR")) }
                    Button("Reconnecting") { model.simulator.select(.reconnecting) }
                }
            }
            #endif
        }.formStyle(.grouped)
    }
}

struct AboutView: View {
    @ObservedObject var model: AppModel
    var body: some View {
        Form {
            Section { Logo(); Text("PrettyLisaVPN").font(.title.bold()); Text(model.version); LabeledContent("Backend", value: model.backendVersion ?? L("unavailable")) }
            Section("FAQ") {
                ForEach(["free", "support"], id: \.self) { key in
                    DisclosureGroup(L("faq_\(key)_q")) { Text(L("faq_\(key)_a")).textSelection(.enabled) }
                }
                DisclosureGroup(L("apple_network_policy")) { Text(L("apple_full_tunnel")) }
            }
            Section {
                Link("prettylisavpn.com", destination: URL(string: "https://prettylisavpn.com")!)
                Button(L("about_contact_support")) { model.page = .support }
                Text(L("apple_licenses")).font(.footnote)
            }
        }.formStyle(.grouped)
    }
}

struct ErrorBanner: View {
    let code: String
    let dismiss: () -> Void
    var body: some View {
        HStack(alignment: .top) {
            Image(systemName: "exclamationmark.triangle")
            VStack(alignment: .leading) { Text(errorText(code)); Text(code).font(.caption.monospaced()) }
            Spacer()
            Button(action: dismiss) { Image(systemName: "xmark") }.accessibilityLabel(L("ui_close"))
        }.padding().background(Color.red.opacity(0.14), ignoresSafeAreaEdges: []).accessibilityElement(children: .contain)
    }
}
func errorText(_ code: String) -> String {
    let key = ["otp_invalid_or_expired": "error_1", "otp_rate_limited": "error_2", "device_limit_reached": "error_3",
               "device_revoked": "error_4", "user_blocked": "error_5", "REAUTH_REQUIRED": "error_6", "invalid_session": "error_6",
               "SECURE_STORAGE_UNAVAILABLE": "error_7", "ROTATION_UNCERTAIN": "error_8", "NETWORK_UNCERTAIN": "error_0", "TIMEOUT": "error_0",
               "PHYSICAL_DEVICE_REQUIRED": "apple_physical_required", "CLEANUP_UNCONFIRMED": "vpn_cleanup", "LOCAL_TEARDOWN_UNCONFIRMED": "vpn_cleanup",
               "ATTACHMENT_REJECTED": "error_14", "INVALID_REQUEST": "error_15", "INTERNET_UNVERIFIED": "vpn_failed"][code] ?? "error_9"
    return L(key)
}
func formatDate(_ value: String) -> String { WireJSON.date(value)?.formatted(date: .abbreviated, time: .shortened) ?? L("unavailable") }
func money(_ minor: Int64, _ currency: String) -> String { (Decimal(minor) / 100).formatted(.currency(code: currency)) }
