import XCTest
@testable import PrettyLisaCore

final class MessageTests: XCTestCase {
    private func inbox(mode: String = "REQUIRE_LINK", url: String = "https://prettylisavpn.com/#latest", schema: Int = 2) throws -> Messages {
        let message: [String: Any] = ["id": "88888888-8888-4888-8888-888888888888", "revision": 1,
            "title": "Update", "blocks": [["type": "paragraph", "text": "Body"]],
            "fallback_text": "Body", "dismiss_label": "OK", "dismissal_mode": mode,
            "links": [["label": "Download", "url": url]]]
        return try WireJSON.decode(Messages.self, from: JSONSerialization.data(withJSONObject: ["schema_version": schema, "messages": [message]]))
    }
    func testAllThreeCloseModesAndFreshVisits() throws {
        let required = try inbox(); try required.validate()
        let message = required.messages[0]
        var visit = MessageVisit(); visit.deferMessage(message)
        XCTAssertNotNil(visit.next(required.messages)); XCTAssertFalse(visit.canClose(message))
        visit.linkOpened(message); XCTAssertTrue(visit.canClose(message))
        visit.deferMessage(message); XCTAssertNil(visit.next(required.messages))
        XCTAssertNotNil(MessageVisit().next(required.messages)); XCTAssertFalse(MessageVisit().canClose(message))
        let repeated = try inbox(mode: "NEXT_VISIT"); try repeated.validate()
        var repeatVisit = MessageVisit(); repeatVisit.deferMessage(repeated.messages[0])
        XCTAssertNil(repeatVisit.next(repeated.messages)); XCTAssertNotNil(MessageVisit().next(repeated.messages))
        let once = try inbox(mode: "ONCE"); try once.validate()
        var onceVisit = MessageVisit(); onceVisit.deferMessage(once.messages[0])
        XCTAssertNotNil(onceVisit.next(once.messages)); XCTAssertTrue(once.messages[0].canAcknowledge)
        XCTAssertFalse(message.canAcknowledge); XCTAssertFalse(repeated.messages[0].canAcknowledge)
        XCTAssertThrowsError(try inbox(mode: "UNKNOWN").validate())
    }
    func testBundledPopupPublicationsValidateBeforeFiltering() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let inbox = try WireJSON.decode(Messages.self, from: Data(contentsOf: root.appendingPathComponent("Resources/Fixtures/messages.json")))
        try inbox.validate()
        XCTAssertEqual(Set(inbox.messages.compactMap { $0.dismissal_mode?.rawValue }), ["REQUIRE_LINK", "NEXT_VISIT", "ONCE"])
    }
    func testSafeLinksAndLegacyContract() throws {
        for url in ["http://example.com", "javascript:alert(1)", "file:///tmp/a", "https://user@example.com", "https://@example.com", "https://example.com:8443", "https://example.com\\@evil.com", "https://example.com/\n"] {
            XCTAssertThrowsError(try inbox(url: url).validate(), url)
        }
        let legacy = Data("""
        {"schema_version":1,"messages":[{"id":"88888888-8888-4888-8888-888888888888","revision":1,"title":"News","blocks":[{"type":"paragraph","text":"Body"}],"fallback_text":"Body","dismiss_label":"OK"}]}
        """.utf8)
        let parsed = try WireJSON.decode(Messages.self, from: legacy); try parsed.validate()
        XCTAssertTrue(MessageVisit().canClose(parsed.messages[0]))
        let upgraded = Data(String(decoding: legacy, as: UTF8.self).replacingOccurrences(of: "schema_version\":1", with: "schema_version\":2").utf8)
        XCTAssertThrowsError(try WireJSON.decode(Messages.self, from: upgraded).validate())
    }
    func testReceiptMustMatchAccountMessageRevision() throws {
        let message = try inbox(mode: "ONCE").messages[0]
        let data = Data("""
        {"id":"88888888-8888-4888-8888-888888888888","revision":2,"acknowledged":true}
        """.utf8)
        XCTAssertThrowsError(try WireJSON.decode(MessageReceipt.self, from: data).validate(for: message))
    }
}
