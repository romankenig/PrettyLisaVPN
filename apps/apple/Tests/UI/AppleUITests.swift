import XCTest

final class AppleUITests: XCTestCase {
    func testSimulatorClearlyLabelsSimulation() {
        let app = XCUIApplication()
        app.launchArguments = ["-ui-fixtures", "-simulate-vpn", "-AppleLanguages", "(ru)"]
        app.launch()
        XCTAssertTrue(app.staticTexts["simulation-banner"].waitForExistence(timeout: 15))
        if !app.buttons["connect"].isHittable {
            let home = app.descendants(matching: .any)["nav-home"].firstMatch
            XCTAssertTrue(home.waitForExistence(timeout: 10)); home.tap()
        }
        let status = app.staticTexts["vpn-status"]
        XCTAssertTrue(status.waitForExistence(timeout: 10))
        let disconnected = status.label
        app.buttons["connect"].tap()
        expectation(for: NSPredicate(format: "enabled == false"), evaluatedWith: app.buttons["connect"])
        waitForExpectations(timeout: 5)
        XCTAssertNotEqual(status.label, disconnected)
        XCTAssertTrue(app.staticTexts["simulation-banner"].exists)
        app.buttons["disconnect"].tap()
        expectation(for: NSPredicate(format: "label == %@", disconnected), evaluatedWith: status)
        waitForExpectations(timeout: 5)
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "simulator-explicit-fixture"; shot.lifetime = .keepAlways; add(shot)
    }
    func testDefaultLaunchShowsRealOTPForm() {
        let app = XCUIApplication(); app.launch()
        XCTAssertTrue(app.textFields["email"].waitForExistence(timeout: 15))
        XCTAssertFalse(app.staticTexts["simulation-banner"].exists)
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "real-api-login-no-vpn-proof"; shot.lifetime = .keepAlways; add(shot)
    }
}
