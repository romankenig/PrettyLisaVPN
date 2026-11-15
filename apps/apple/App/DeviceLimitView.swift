import SwiftUI

/// The restricted cabinet does not mount VPN, billing, support or message screens.
struct DeviceLimitView: View {
    @ObservedObject var model: AppModel
    @State private var logout = false
    @State private var forget = false
    var body: some View {
        VStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 12) {
                Text(L("device_limit")).font(.headline).foregroundStyle(Color(red: 0.78, green: 0.17, blue: 0.16))
                Text(L("device_limit_help")).foregroundStyle(Color(red: 0.78, green: 0.17, blue: 0.16))
                Button(L("manage_devices")) { model.page = .devices }.buttonStyle(.borderedProminent)
                    .disabled(model.busy).accessibilityIdentifier("limit-manage-devices")
            }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(red: 1, green: 0.95, blue: 0.94), in: RoundedRectangle(cornerRadius: 18))
                .accessibilityIdentifier("device-limit-banner")
            if model.page == .devices {
                #if os(iOS)
                IOSDevicesView(model: model)
                #else
                DevicesView(model: model)
                #endif
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        Text(model.profile?.email ?? "").font(.headline).textSelection(.enabled)
                        Text("\(model.profile?.plan ?? "") \(model.profile?.plan == "PLATINUM" ? "💎" : model.profile?.plan == "PREMIUM" ? "⭐" : "🕊️")").font(.headline)
                        Button("\(L("ui_devices")) · \(model.profile?.active_device_count ?? 5) / 5 →") { model.page = .devices }
                            .accessibilityIdentifier("limit-device-count")
                        VStack(alignment: .leading, spacing: 14) {
                            Text(L("ui_where_to_connect")).font(.headline)
                            Button(L("ui_autopilot")) { }
                            Button(L("dash_connect")) { }.accessibilityIdentifier("limit-connect")
                            Button(L("ui_subscription")) { }
                            Button(L("advanced_settings")) { }
                        }.buttonStyle(.borderedProminent).disabled(true).opacity(0.45)
                        Button(L("manage_devices")) { model.page = .devices }
                    }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
                        .foregroundStyle(.black).background(Color(red: 0.894, green: 0.894, blue: 0.894), in: RoundedRectangle(cornerRadius: 18))
                }
            }
            HStack {
                Button(L("ui_sign_out")) { logout = true }.accessibilityIdentifier("limit-logout")
                Button(L("forget_local")) { forget = true }.accessibilityIdentifier("limit-forget")
            }.buttonStyle(.bordered).disabled(model.busy)
        }.padding(16)
            .confirmationDialog(L("ui_sign_out_54"), isPresented: $logout, titleVisibility: .visible) {
                Button(L("ui_sign_out"), role: .destructive) { model.logout() }
            }
            .confirmationDialog(L("ui_remove_local_session"), isPresented: $forget, titleVisibility: .visible) {
                Button(L("ui_remove_and_sign_in"), role: .destructive) { model.forget() }
            } message: { Text(L("ui_this_removes_local_credentials_and_opens_sign_in_it_does_not_conf")) }
    }
}
