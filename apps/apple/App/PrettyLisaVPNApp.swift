import SwiftUI

@main @MainActor struct PrettyLisaVPNApp: App {
    @StateObject private var holder = AppHolder()
    @AppStorage("theme") private var theme = "system"
    var body: some Scene {
        #if os(macOS)
        Window("PrettyLisaVPN", id: "main") {
            content.frame(minWidth: 760, minHeight: 600)
                .onChange(of: theme, initial: true) { _, selected in
                    // Apply the preference to AppKit chrome, menus and Settings too.
                    NSApplication.shared.appearance = selected == "dark" ? NSAppearance(named: .darkAqua)
                        : selected == "light" ? NSAppearance(named: .aqua) : nil
                }
        }
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
        #else
        WindowGroup { content }
        #endif
    }
    @ViewBuilder private var content: some View {
        if let model = holder.model {
            RootView(model: model)
                #if os(iOS)
                .preferredColorScheme(.dark)
                #else
                .preferredColorScheme(theme == "dark" ? .dark : theme == "light" ? .light : nil)
                #endif
        } else {
            ContentUnavailableView("PrettyLisaVPN", systemImage: "exclamationmark.triangle", description: Text(L("apple_configuration_error")))
        }
    }
}
@MainActor final class AppHolder: ObservableObject {
    let model: AppModel? = try? AppModel()
}
