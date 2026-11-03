import XCTest

final class AppleUITests: XCTestCase {
    func testSimulatorClearlyLabelsSimulation() {
        let app = XCUIApplication()
        app.launchArguments = ["-ui-fixtures", "-simulate-vpn", "-AppleLanguages", "(ru)"]
        app.launch()
        XCTAssertTrue(app.staticTexts["simulation-banner"].waitForExistence(timeout: 15))
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
