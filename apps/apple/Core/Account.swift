import Foundation

public struct Price: Codable, Sendable { public let amount_minor: Int64; public let original_amount_minor: Int64?; public let currency: String? }
public struct Offer: Codable, Identifiable, Sendable { public let id: UUID; public let prices: [String: Price] }
public struct BillingOverview: Codable, Sendable {
    public let revision: String
    public let provider_mode: String?
    public let payment_operations_available: Bool?
    public let plan: String
    public let status: String
    public let paid_until: String?
    public let auto_renew: Bool
    public let current_price: Price?
    public let offers: [Offer]
    public let actions: [String]
    public let pending_operation_id: UUID?
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
public struct Messages: Codable, Sendable { public let schema_version: Int; public let messages: [AccountMessage] }
public struct SupportReceipt: Codable, Sendable { public let request_id: UUID; public let status: String }
public struct SupportReport: Codable, Sendable {
    public let request_id: UUID
    public let subject: String
    public let description: String
    public let reply_email: String
    public let diagnostics: String? = nil
    public init(id: UUID, subject: String, description: String, email: String) {
        request_id = id; self.subject = subject; self.description = description; reply_email = email
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
