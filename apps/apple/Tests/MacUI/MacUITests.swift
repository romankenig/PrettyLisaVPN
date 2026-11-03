import XCTest

final class MacUITests: XCTestCase {
    func testNativeWindowAndAppearance() {
        for theme in ["light", "dark"] {
            let app = XCUIApplication()
            app.launchArguments = ["-ui-fixtures", "-theme", theme]
            app.launch()
            XCTAssertTrue(app.windows.firstMatch.waitForExistence(timeout: 20))
            let attachment = XCTAttachment(screenshot: app.windows.firstMatch.screenshot())
            attachment.name = "macOS-\(theme)-fixture-not-vpn-proof"
            attachment.lifetime = .keepAlways; add(attachment)
            app.terminate()
        }
    }
}
