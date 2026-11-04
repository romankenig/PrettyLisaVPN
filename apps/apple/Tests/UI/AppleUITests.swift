import XCTest

final class AppleUITests: XCTestCase {
    func testSimulatorClearlyLabelsSimulation() {
        for theme in ["light", "dark"] { reviewSimulation(theme: theme) }
    }
    private func reviewSimulation(theme: String) {
        let app = XCUIApplication()
        app.launchArguments = ["-ui-fixtures", "YES", "-simulate-vpn", "YES", "-AppleLanguages", "(ru)", "-theme", theme]
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
        XCTAssertTrue(app.buttons["disconnect"].waitForExistence(timeout: 5))
        XCTAssertNotEqual(status.label, disconnected)
        XCTAssertTrue(app.staticTexts["simulation-banner"].exists)
        app.buttons["disconnect"].tap()
        expectation(for: NSPredicate(format: "label == %@", disconnected), evaluatedWith: status)
        waitForExpectations(timeout: 5)
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "simulator-\(theme)-explicit-fixture"; shot.lifetime = .keepAlways; add(shot)
        app.terminate()
    }
    func testReferenceNavigationAndScreens() {
        for theme in ["light", "dark"] {
            let app = XCUIApplication()
            app.launchArguments = ["-ui-fixtures", "YES", "-AppleLanguages", "(ru)", "-language", "ru", "-theme", theme]
            app.launch()
            XCTAssertTrue(app.buttons["nav-settings"].waitForExistence(timeout: 15))
            XCTAssertFalse(app.staticTexts["simulation-banner"].exists)
            capture(app, "reference-home-\(theme)")
            app.buttons["connect"].tap()
            XCTAssertTrue(app.staticTexts["FIXTURE_NO_VPN"].waitForExistence(timeout: 5))
            XCTAssertFalse(app.buttons["disconnect"].exists)
            app.buttons["закрыть"].tap()
            app.buttons["nav-settings"].tap()
            XCTAssertTrue(app.buttons["settings-devices"].waitForExistence(timeout: 5))
            capture(app, "reference-settings-\(theme)")
            app.buttons["settings-devices"].tap()
            XCTAssertTrue(app.staticTexts["iPhone Preview"].waitForExistence(timeout: 5))
            XCTAssertFalse(app.buttons["device-revoke"].isEnabled)
            capture(app, "reference-devices-\(theme)")
            app.buttons["nav-back"].tap()
            app.buttons["settings-advanced"].tap()
            XCTAssertTrue(app.switches["WireGuard"].waitForExistence(timeout: 5))
            app.buttons["nav-back"].tap()
            app.buttons["nav-about"].tap()
            XCTAssertTrue(app.buttons["about-support"].waitForExistence(timeout: 5))
            capture(app, "reference-about-\(theme)")
            app.buttons["about-support"].tap()
            XCTAssertTrue(app.textFields["тема"].waitForExistence(timeout: 5))
            app.buttons["nav-back"].tap()
            app.buttons["nav-home"].tap()
            XCTAssertTrue(app.buttons["connect"].waitForExistence(timeout: 5))
            app.terminate()
        }
    }
    private func capture(_ app: XCUIApplication, _ name: String) {
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = name; shot.lifetime = .keepAlways; add(shot)
    }
    func testDefaultLaunchShowsRealOTPForm() {
        for theme in ["light", "dark"] {
            let app = XCUIApplication(); app.launchArguments = ["-theme", theme]; app.launch()
            XCTAssertTrue(app.textFields["email"].waitForExistence(timeout: 15))
            XCTAssertFalse(app.staticTexts["simulation-banner"].exists)
            let shot = XCTAttachment(screenshot: app.screenshot())
            shot.name = "real-api-login-\(theme)-no-vpn-proof"; shot.lifetime = .keepAlways; add(shot)
            app.terminate()
        }
    }
}
