import SwiftUI
import PrettyLisaCore

struct AccountMessagePopup: View {
    @ObservedObject var model: AppModel
    let message: AccountMessage
    @Environment(\.openURL) private var openURL
    @Environment(\.colorScheme) private var colors
    @State private var linkError = false
    private let danger = Color(red: 200 / 255, green: 43 / 255, blue: 40 / 255)
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text(message.title).font(.title2.bold()).accessibilityIdentifier("message-title")
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(message.body).frame(maxWidth: .infinity, alignment: .leading)
                    ForEach(Array((message.links ?? []).enumerated()), id: \.offset) { index, link in
                        Button(link.label) {
                            linkError = false
                            do {
                                let url = try link.validatedURL()
                                let visitID = model.messageVisit.id
                                openURL(url) { accepted in
                                    linkError = !accepted
                                    if accepted && model.messageVisit.id == visitID { model.messageVisit.linkOpened(message) }
                                }
                            } catch { linkError = true }
                        }.accessibilityIdentifier("message-link-\(index)")
                    }
                    if linkError { Text(L("message_link_error")).foregroundStyle(danger) }
                    if model.messageError { Text(L("message_ack_error")).foregroundStyle(danger) }
                }
            }
            if model.messageVisit.canClose(message) {
                HStack {
                    if message.dismissal_mode == nil {
                        Button(L("ui_later")) { model.deferMessage(message) }.disabled(model.messageBusy).accessibilityIdentifier("message-later")
                    }
                    Spacer()
                    Button(message.dismiss_label) {
                        if message.dismissal_mode == nil { model.acknowledge(message) } else { model.closeMessage(message) }
                    }
                        .disabled(model.messageBusy).accessibilityIdentifier("message-ack")
                }
                if let action = message.primary_action, ["OPEN_SUBSCRIPTION", "OPEN_SETTINGS", "OPEN_ABOUT"].contains(action.type) {
                    Button(action.label) { model.acknowledge(message, navigate: true) }.disabled(model.messageBusy)
                }
            }
        }
        .padding(24).frame(minWidth: 280, idealWidth: 480, maxWidth: 580, minHeight: 300, idealHeight: 480)
        .tint(colors == .dark ? Color(red: 172 / 255, green: 115 / 255, blue: 1) : Color(red: 95 / 255, green: 34 / 255, blue: 217 / 255))
        .task(id: message.key) {
            guard let expiry = message.expires_at.flatMap(WireJSON.date) else { return }
            while expiry > Date() {
                do { try await Task.sleep(nanoseconds: UInt64(min(60, max(0.01, expiry.timeIntervalSinceNow)) * 1_000_000_000)) }
                catch { return }
            }
            model.messageNow = Date()
        }
        #if os(macOS)
        .onExitCommand { model.closeMessage(message) }
        #endif
    }
}
