import Foundation

public struct Price: Codable, Sendable { public let amount_minor: Int64; public let original_amount_minor: Int64?; public let currency: String? }
public struct Offer: Codable, Identifiable, Sendable { public let id: UUID; public let prices: [String: Price] }
public struct BillingPaymentMethod: Codable, Sendable {
    public let label: String
    public let kind: String?
    public let card_brand: String?
    public let card_last4: String?
    public var summary: String? {
        guard label.count <= 128, label.filter({ $0.isNumber }).count <= 4 else { return nil }
        if kind == "CARD" {
            let brands = ["visa": "Visa", "mastercard": "Mastercard", "mir": "МИР", "unknown": ""]
            guard let last4 = card_last4, last4.count == 4, last4.allSatisfy({ "0123456789".contains($0) }),
                  let name = brands[card_brand ?? ""] else { return nil }
            return "\(name) •••• \(last4)".trimmingCharacters(in: .whitespaces)
        }
        guard kind == nil || kind == "UNKNOWN" || kind == "SBP", card_brand == nil, card_last4 == nil else { return nil }
        return label
    }
}
public struct BillingOverview: Codable, Sendable {
    public let revision: String
    public let provider_mode: String?
    public let payment_operations_available: Bool?
    public let plan: String
    public let status: String
    public let paid_until: String?
    public let auto_renew: Bool
    public let current_price: Price?
    public let payment_method: BillingPaymentMethod?
    public let next_charge_at: String?
    public let next_charge_price: Price?
    public let new_contract_required: Bool?
    public let offers: [Offer]
    public let actions: [String]
    public let pending_operation_id: UUID?
    public func validate() throws {
        if let method = payment_method, method.summary == nil { throw ClientError("INVALID_RESPONSE") }
        if next_charge_at != nil || next_charge_price != nil {
            guard let next = next_charge_at, WireJSON.date(next) != nil, auto_renew,
                  payment_method != nil, let price = next_charge_price, let current = current_price,
                  price.amount_minor > 0, price.amount_minor == current.amount_minor,
                  price.currency == current.currency, ["RUB", "USD"].contains(price.currency ?? "")
            else { throw ClientError("INVALID_RESPONSE") }
        }
    }
}
public enum MessageDismissalMode: String, Codable, Sendable {
    case requireLink = "REQUIRE_LINK", nextVisit = "NEXT_VISIT", once = "ONCE"
}
public struct AccountMessage: Codable, Identifiable, Sendable {
    public struct Action: Codable, Sendable { public let type: String; public let label: String }
    public struct Block: Codable, Sendable { public let type: String; public let text: String?; public let items: [String]? }
    public let id: UUID
    public let revision: Int
    public let title: String
    public let blocks: [Block]
    public let fallback_text: String
    public let primary_action: Action?
    public let dismiss_label: String
    public let expires_at: String?
    public let dismissal_mode: MessageDismissalMode?
    public let links: [MessageLink]?
    public var requiresLink: Bool { dismissal_mode == .requireLink }
    public var canAcknowledge: Bool { dismissal_mode == nil || dismissal_mode == .once }
    public var key: String { "\(id):\(revision)" }
    public func fresh(at now: Date = Date()) -> Bool {
        guard let expiry = expires_at else { return true }
        return WireJSON.date(expiry).map { $0 > now } ?? false
    }
    public var body: String {
        blocks.map { block in
            switch block.type {
            case "paragraph": return block.text ?? fallback_text
            case "list": return block.items?.map { "• " + $0 }.joined(separator: "\n") ?? fallback_text
            default: return fallback_text
            }
        }.joined(separator: "\n\n")
    }
}
public struct MessageLink: Codable, Sendable {
    public let label: String
    public let url: String
    public func validatedURL() throws -> URL {
        guard url.utf16.count <= 2048, url.hasPrefix("https://"),
              !url.contains("\\"), !url.unicodeScalars.contains(where: { CharacterSet.whitespacesAndNewlines.union(.controlCharacters).contains($0) }),
              let components = URLComponents(string: url), let host = components.host, !host.isEmpty,
              components.user == nil, components.password == nil,
              components.port == nil || components.port == 443, let value = components.url
        else { throw ClientError("MESSAGE_URL_NOT_ALLOWED") }
        return value
    }
}
public struct Messages: Codable, Sendable {
    public let schema_version: Int
    public let messages: [AccountMessage]
    public func validate() throws {
        guard (1...2).contains(schema_version), messages.count <= 10,
              Set(messages.map(\.key)).count == messages.count else { throw ClientError("INVALID_RESPONSE") }
        for message in messages {
            guard message.revision > 0, (1...120).contains(message.title.utf16.count),
                  (1...12).contains(message.blocks.count), (1...4000).contains(message.fallback_text.utf16.count),
                  (1...60).contains(message.dismiss_label.utf16.count),
                  message.expires_at == nil || WireJSON.date(message.expires_at!) != nil,
                  schema_version == 1 || (message.dismissal_mode != nil && message.links != nil),
                  (message.links?.count ?? 0) <= 4,
                  !message.requiresLink || !(message.links ?? []).isEmpty,
                  message.canAcknowledge || message.primary_action == nil
            else { throw ClientError("INVALID_RESPONSE") }
            for link in message.links ?? [] {
                guard (1...60).contains(link.label.utf16.count) else { throw ClientError("INVALID_RESPONSE") }
                _ = try link.validatedURL()
            }
        }
    }
}

public struct MessageVisit: Sendable {
    public let id = UUID()
    private var deferred = Set<String>()
    private var openedLinks = Set<String>()
    public init() {}
    public func canClose(_ message: AccountMessage) -> Bool {
        !message.requiresLink || openedLinks.contains(message.key)
    }
    public mutating func linkOpened(_ message: AccountMessage) { openedLinks.insert(message.key) }
    public mutating func deferMessage(_ message: AccountMessage) {
        if canClose(message) && message.dismissal_mode != .once { deferred.insert(message.key) }
    }
    public func next(_ messages: [AccountMessage], now: Date = Date()) -> AccountMessage? {
        messages.first { $0.fresh(at: now) && !deferred.contains($0.key) }
    }
}

public struct MessageReceipt: Decodable {
    public let id: UUID
    public let revision: Int
    public let acknowledged: Bool
    public func validate(for message: AccountMessage) throws {
        guard id == message.id, revision == message.revision, acknowledged else { throw ClientError("INVALID_RESPONSE") }
    }
}
public struct SupportReceipt: Codable, Sendable { public let request_id: UUID; public let status: String }
public struct SupportReport: Codable, Sendable {
    public let request_id: UUID
    public let subject: String
    public let description: String
    public let reply_email: String
    public let diagnostics: String?
    public init(id: UUID, subject: String, description: String, email: String) {
        request_id = id; self.subject = subject; self.description = description; reply_email = email; diagnostics = nil
    }
    public func multipart(images: [SupportImage]) throws -> (body: Data, contentType: String) {
        guard images.count <= 3, images.allSatisfy({ $0.data.count <= 5 * 1024 * 1024 }),
              images.reduce(0, { $0 + $1.data.count }) <= 10 * 1024 * 1024,
              (1...120).contains(subject.count), (1...4000).contains(description.count),
              !subject.contains("\n"), !subject.contains("\r"), !reply_email.contains("\n"), !reply_email.contains("\r")
        else { throw ClientError("INVALID_REQUEST") }
        let boundary = "PrettyLisaVPN-" + UUID().uuidString
        var body = Data()
        func append(_ value: String) { body.append(Data(value.utf8)) }
        append("--\(boundary)\r\nContent-Disposition: form-data; name=\"report\"\r\n\r\n")
        // diagnostics:null is required by the shared API; Apple does not claim WINDOWS diagnostics.
        var object = try JSONSerialization.jsonObject(with: WireJSON.encode(self)) as! [String: Any]
        object["diagnostics"] = NSNull()
        body.append(try JSONSerialization.data(withJSONObject: object))
        append("\r\n")
        for (index, image) in images.enumerated() {
            guard ["image/png", "image/jpeg", "image/webp"].contains(image.type) else { throw ClientError("ATTACHMENT_REJECTED") }
            append("--\(boundary)\r\nContent-Disposition: form-data; name=\"screenshots\"; filename=\"screenshot-\(index)\"\r\nContent-Type: \(image.type)\r\n\r\n")
            body.append(image.data); append("\r\n")
        }
        append("--\(boundary)--\r\n")
        return (body, "multipart/form-data; boundary=" + boundary)
    }
}
public struct SupportImage: Codable, Sendable {
    public let data: Data
    public let type: String
    public init(data: Data, type: String) { self.data = data; self.type = type }
}

public struct BillingPortal: Decodable, Sendable {
    public let url: String
    public func validatedURL() throws -> URL {
        guard url.range(of: "^https://prettylisavpn\\.com/account/#handoff=[A-Za-z0-9_-]{43}$", options: .regularExpression) != nil,
              let value = URL(string: url) else { throw ClientError("PAYMENT_URL_NOT_ALLOWED") }
        return value
    }
}
