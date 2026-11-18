import SwiftUI

/// The shared catalogue supplies the text and an allowlisted target for each link.
struct FAQAnswer: View {
    let entry: FAQEntry
    let support: () -> Void

    private var answer: AttributedString {
        let source = L("faq_\(entry.id)_a")
        let pattern = try! NSRegularExpression(pattern: "\\[([^\\]]+)\\]")
        let matches = pattern.matches(in: source, range: NSRange(source.startIndex..., in: source))
        var result = AttributedString()
        var cursor = source.startIndex
        for (index, match) in matches.enumerated() {
            guard let range = Range(match.range, in: source),
                  let label = Range(match.range(at: 1), in: source),
                  entry.links.indices.contains(index) else { continue }
            result += AttributedString(String(source[cursor..<range.lowerBound]))
            var link = AttributedString(String(source[label]))
            link.link = entry.links[index] == "support"
                ? URL(string: "prettylisavpn-faq://support") : paymentURL
            result += link
            cursor = range.upperBound
        }
        result += AttributedString(String(source[cursor...]))
        return result
    }

    private var paymentURL: URL {
        let selected = UserDefaults.standard.string(forKey: "language") ?? "system"
        let locale = selected == "system" ? (Bundle.main.preferredLocalizations.first ?? "en") : selected
        let language = locale == "zh-Hans" ? "zh" : locale
        let safe = ["ru", "en", "de", "fr", "es", "zh"].contains(language) ? language : "en"
        return URL(string: "https://prettylisavpn.com" + (safe == "ru" ? "" : "/\(safe)") + "/legal/payments/")!
    }

    var body: some View {
        Text(answer)
            .fixedSize(horizontal: false, vertical: true)
            .lineSpacing(5)
            .textSelection(.enabled)
            .environment(\.openURL, OpenURLAction { url in
                if url.absoluteString == "prettylisavpn-faq://support" {
                    support()
                    return .handled
                }
                return .systemAction
            })
    }
}
