import XCTest
@testable import PrettyLisaCore

final class MessageTests: XCTestCase {
    private func inbox(dismissible: Bool = false, url: String = "https://prettylisavpn.com/#latest", schema: Int = 2) throws -> Messages {
        let message: [String: Any] = ["id": "88888888-8888-4888-8888-888888888888", "revision": 1,
            "title": "Update", "blocks": [["type": "paragraph", "text": "Body"]],
            "fallback_text": "Body", "dismiss_label": "OK", "dismissible": dismissible,
            "links": [["label": "Download", "url": url]]]
        return try WireJSON.decode(Messages.self, from: JSONSerialization.data(withJSONObject: ["schema_version": schema, "messages": [message]]))
    }
    func testMandatoryCannotBeDeferredAndNewVisitsRestoreOptional() throws {
        let required = try inbox(); try required.validate()
        var visit = MessageVisit(); visit.deferMessage(required.messages[0])
        XCTAssertEqual(visit.next(required.messages)?.id, required.messages[0].id)
        let optional = try inbox(dismissible: true); try optional.validate()
        visit.deferMessage(optional.messages[0]); XCTAssertNil(visit.next(optional.messages))
        XCTAssertNotNil(MessageVisit().next(optional.messages))
        // A required revision cannot be bypassed by a former account-wide read flag.
        XCTAssertNotNil(visit.next(required.messages))
    }
    func testSafeLinksAndLegacyContract() throws {
        for url in ["http://example.com", "javascript:alert(1)", "file:///tmp/a", "https://user@example.com", "https://@example.com", "https://example.com:8443", "https://example.com\\@evil.com", "https://example.com/\n"] {
            XCTAssertThrowsError(try inbox(url: url).validate(), url)
        }
        let legacy = Data("""
        {"schema_version":1,"messages":[{"id":"88888888-8888-4888-8888-888888888888","revision":1,"title":"News","blocks":[{"type":"paragraph","text":"Body"}],"fallback_text":"Body","dismiss_label":"OK"}]}
        """.utf8)
        let parsed = try WireJSON.decode(Messages.self, from: legacy); try parsed.validate()
        XCTAssertTrue(parsed.messages[0].canDismiss)
        let upgraded = Data(String(decoding: legacy, as: UTF8.self).replacingOccurrences(of: "schema_version\":1", with: "schema_version\":2").utf8)
        XCTAssertThrowsError(try WireJSON.decode(Messages.self, from: upgraded).validate())
    }
    func testReceiptMustMatchAccountMessageRevision() throws {
        let message = try inbox(dismissible: true).messages[0]
        let data = Data("""
        {"id":"88888888-8888-4888-8888-888888888888","revision":2,"acknowledged":true}
        """.utf8)
        XCTAssertThrowsError(try WireJSON.decode(MessageReceipt.self, from: data).validate(for: message))
    }
}
