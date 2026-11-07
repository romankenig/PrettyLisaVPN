import Foundation
import XCTest
@testable import PrettyLisaCore

final class BillingTests: XCTestCase {
    func testPortalRequiresFixedOriginPathAndFragment() throws {
        let url = "https://prettylisavpn.com/account/#handoff=" + String(repeating: "a", count: 43)
        let portal = BillingPortal(url: url)
        XCTAssertEqual(try portal.validatedURL().absoluteString, url)
        for value in [url.replacingOccurrences(of: ".com", with: ".com.evil.test"), url.replacingOccurrences(of: "#", with: "?"), url + "&redirect=evil"] {
            XCTAssertThrowsError(try BillingPortal(url: value).validatedURL())
        }
    }
    func testCardSummaryExposesOnlyBrandAndLastFour() throws {
        let value = try WireJSON.decode(BillingPaymentMethod.self, from: Data(#"{"kind":"CARD","label":"Visa •••• 4242","card_brand":"visa","card_last4":"4242"}"#.utf8))
        XCTAssertEqual(value.summary, "Visa •••• 4242")
        for json in [
            #"{"label":"4242 4242 4242 4242"}"#,
            #"{"kind":"CARD","label":"Visa","card_brand":"visa","card_last4":"4242424242424242"}"#,
            #"{"kind":"SBP","label":"SBP","card_brand":"visa","card_last4":"4242"}"#
        ] { XCTAssertNil(try WireJSON.decode(BillingPaymentMethod.self, from: Data(json.utf8)).summary) }
    }
    func testNextPaymentCannotUseANewCatalogPrice() throws {
        let json = #"{"revision":"test","plan":"PREMIUM","status":"ACTIVE","paid_until":"2027-01-01T00:00:00Z","auto_renew":true,"current_price":{"amount_minor":12345,"currency":"RUB"},"next_charge_at":"2027-01-01T00:00:00Z","next_charge_price":{"amount_minor":54321,"currency":"RUB"},"payment_method":{"label":"Visa •••• 4242","kind":"CARD","card_brand":"visa","card_last4":"4242"},"offers":[],"actions":[]}"#
        let invalid = try WireJSON.decode(BillingOverview.self, from: Data(json.utf8))
        XCTAssertThrowsError(try invalid.validate())
        let valid = try WireJSON.decode(BillingOverview.self, from: Data(json.replacingOccurrences(of: "54321", with: "12345").utf8))
        XCTAssertNoThrow(try valid.validate())
    }
}
