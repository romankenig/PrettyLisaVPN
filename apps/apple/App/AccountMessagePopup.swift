import SwiftUI
import PrettyLisaCore

struct AccountMessagePopup: View {
    @ObservedObject var model: AppModel
    let message: AccountMessage
    @Environment(\.openURL) private var openURL
    @State private var linkError = false
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
                                openURL(url) { accepted in linkError = !accepted }
                            } catch { linkError = true }
                        }.accessibilityIdentifier("message-link-\(index)")
                    }
                    if linkError { Text(L("message_link_error")).foregroundStyle(.red) }
                    if model.messageError { Text(L("message_ack_error")).foregroundStyle(.red) }
                }
            }
            if message.canDismiss {
                HStack {
                    Button(L("ui_later")) { model.deferMessage(message) }.accessibilityIdentifier("message-later")
                    Spacer()
                    Button(message.dismiss_label) { model.acknowledge(message) }
                        .disabled(model.messageBusy).accessibilityIdentifier("message-ack")
                }
                if let action = message.primary_action, ["OPEN_SUBSCRIPTION", "OPEN_SETTINGS", "OPEN_ABOUT"].contains(action.type) {
                    Button(action.label) { model.acknowledge(message, navigate: true) }.disabled(model.messageBusy)
                }
            }
        }
        .padding(24).frame(minWidth: 280, idealWidth: 480, maxWidth: 580, minHeight: 300, idealHeight: 480)
        .task(id: message.key) {
            guard let expiry = message.expires_at.flatMap(WireJSON.date) else { return }
            while expiry > Date() {
                do { try await Task.sleep(nanoseconds: UInt64(min(60, max(0.01, expiry.timeIntervalSinceNow)) * 1_000_000_000)) }
                catch { return }
            }
            model.messageNow = Date()
        }
        #if os(macOS)
        .onExitCommand { if message.canDismiss { model.deferMessage(message) } }
        #endif
    }
}
