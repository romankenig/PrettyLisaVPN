import SwiftUI

@main struct PrettyLisaVPNApp: App {
    @StateObject private var holder = AppHolder()
    @AppStorage("theme") private var theme = "system"
    var body: some Scene {
        WindowGroup {
            if let model = holder.model {
                RootView(model: model)
                    .preferredColorScheme(theme == "dark" ? .dark : theme == "light" ? .light : nil)
                    #if os(macOS)
                    .frame(minWidth: 760, minHeight: 600)
                    #endif
            } else { ContentUnavailableView("PrettyLisaVPN", systemImage: "exclamationmark.triangle", description: Text(L("apple_configuration_error"))) }
        }
        #if os(macOS)
        .defaultSize(width: 1000, height: 740)
        .commands {
            CommandGroup(after: .appInfo) { Button(L("about")) { holder.model?.page = .about } }
            CommandMenu("VPN") {
                Button(L("dash_connect")) { holder.model?.connect() }.keyboardShortcut("k", modifiers: [.command])
                Button(L("vpn_disconnect")) { Task { await holder.model?.disconnect() } }.keyboardShortcut("k", modifiers: [.command, .shift])
                Button(L("ui_refresh")) { Task { await holder.model?.loadPage() } }.keyboardShortcut("r", modifiers: [.command])
            }
        }
        Settings { if let model = holder.model { SettingsView(model: model).frame(width: 480, height: 560) } }
        #endif
    }
}
@MainActor final class AppHolder: ObservableObject {
    let model: AppModel? = try? AppModel()
}
