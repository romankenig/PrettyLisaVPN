import XCTest

final class MacUITests: XCTestCase {
    func testDefaultLaunchShowsRealOTPForm() {
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.windows.firstMatch.waitForExistence(timeout: 20))
        XCTAssertTrue(app.textFields["email"].waitForExistence(timeout: 10))
        app.terminate()
    }
    func testFixtureWithoutAppearanceOverride() {
        let app = XCUIApplication(); app.launchArguments = ["-ui-fixtures", "YES"]; app.launch()
        XCTAssertTrue(app.windows.firstMatch.waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["vpn-status"].waitForExistence(timeout: 10))
        app.terminate()
    }
    func testForcedAppearanceWithoutFixtures() {
        let app = XCUIApplication(); app.launchArguments = ["-theme", "light"]; app.launch()
        XCTAssertTrue(app.windows.firstMatch.waitForExistence(timeout: 20))
        XCTAssertTrue(app.textFields["email"].waitForExistence(timeout: 10))
        app.terminate()
    }
    func testNativeWindowAndAppearance() {
        for theme in ["light", "dark"] {
            let app = XCUIApplication()
            // AppKit interprets a value-less defaults flag as consuming the next
            // argument, leaving the theme value as a document to open.
            app.launchArguments = ["-ui-fixtures", "YES", "-theme", theme]
            app.launch()
            let window = app.windows.firstMatch
            guard window.waitForExistence(timeout: 20) else {
                let hierarchy = XCTAttachment(string: app.debugDescription)
                hierarchy.name = "macOS-missing-window-hierarchy"; hierarchy.lifetime = .keepAlways; add(hierarchy)
                let screen = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
                screen.name = "macOS-missing-window-screen"; screen.lifetime = .keepAlways; add(screen)
                XCTFail("PrettyLisaVPN launched without an accessible native window")
                return
            }
            XCTAssertTrue(app.staticTexts["vpn-status"].waitForExistence(timeout: 15))
            let attachment = XCTAttachment(screenshot: window.screenshot())
            attachment.name = "macOS-\(theme)-fixture-not-vpn-proof"
            attachment.lifetime = .keepAlways; add(attachment)
            let originalWidth = window.frame.width
            let corner = window.coordinate(withNormalizedOffset: CGVector(dx: 1, dy: 1)).withOffset(CGVector(dx: -2, dy: -2))
            corner.click(forDuration: 0.2, thenDragTo: corner.withOffset(CGVector(dx: -160, dy: -90)))
            XCTAssertLessThan(window.frame.width, originalWidth - 50)
            for page in ["devices", "subscription", "support", "settings", "about", "home"] {
                let item = app.descendants(matching: .any)["nav-" + page].firstMatch
                XCTAssertTrue(item.exists); item.click()
            }
            XCTAssertTrue(app.staticTexts["vpn-status"].waitForExistence(timeout: 5))
            let resized = XCTAttachment(screenshot: window.screenshot())
            resized.name = "macOS-\(theme)-resized-fixture"; resized.lifetime = .keepAlways; add(resized)
            app.terminate()
        }
    }
}
