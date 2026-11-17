import XCTest

final class MacUITests: XCTestCase {
    func testAccountMessagePopups() {
        for mode in ["once", "repeat", "mandatory"] {
            let app = XCUIApplication()
            app.launchArguments = ["-ui-fixtures", "YES", "-message-fixture", "YES", "-language", "ru"]
            if mode != "once" { app.launchArguments += ["-\(mode)-message", "YES"] }
            app.launch()
            XCTAssertTrue(app.staticTexts["message-title"].waitForExistence(timeout: 20))
            XCTAssertTrue(app.buttons["message-link-0"].exists)
            let shot = XCTAttachment(screenshot: app.windows.firstMatch.screenshot())
            shot.name = "macOS-message-\(mode)"; shot.lifetime = .keepAlways; add(shot)
            XCTAssertFalse(app.buttons["message-later"].exists)
            if mode == "mandatory" {
                XCTAssertFalse(app.buttons["message-ack"].exists)
                app.typeKey(.escape, modifierFlags: [])
                XCTAssertTrue(app.staticTexts["message-title"].exists)
                app.buttons["message-link-0"].click()
                let browser = XCUIApplication(bundleIdentifier: "com.apple.Safari")
                XCTAssertTrue(browser.wait(for: .runningForeground, timeout: 15))
                app.activate()
                XCTAssertTrue(app.wait(for: .runningForeground, timeout: 10))
                XCTAssertTrue(app.buttons["message-ack"].waitForExistence(timeout: 10))
                let unlocked = XCTAttachment(screenshot: app.windows.firstMatch.screenshot())
                unlocked.name = "macOS-message-link-opened"; unlocked.lifetime = .keepAlways; add(unlocked)
                browser.terminate()
                app.activate()
            }
            app.typeKey(.escape, modifierFlags: [])
            XCTAssertTrue(app.staticTexts["message-title"].waitForNonExistence(timeout: 5))
            if mode != "once" {
                app.terminate(); app.launch()
                XCTAssertTrue(app.staticTexts["message-title"].waitForExistence(timeout: 20))
                XCTAssertEqual(app.buttons["message-ack"].exists, mode == "repeat")
            }
            app.terminate()
        }
    }
    func testPendingCabinetInNativeWindow() {
        let app = XCUIApplication()
        app.launchArguments = ["-ui-fixtures", "YES", "-device-limit-fixture", "YES", "-language", "ru"]
        app.launch()
        XCTAssertTrue(app.buttons["limit-manage-devices"].waitForExistence(timeout: 20))
        XCTAssertFalse(app.buttons["limit-connect"].isEnabled)
        XCTAssertTrue(app.buttons["limit-forget"].exists)
        let shot = XCTAttachment(screenshot: app.windows.firstMatch.screenshot())
        shot.name = "macOS-device-limit-cabinet"; shot.lifetime = .keepAlways; add(shot)
        app.buttons["limit-manage-devices"].tap()
        XCTAssertTrue(app.staticTexts["iPhone Preview"].waitForExistence(timeout: 10))
        app.terminate()
    }
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
            app.launchArguments = ["-ui-fixtures", "YES", "-AppleLanguages", "(ru)", "-theme", theme]
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
                if page == "settings" {
                    let randomize = app.buttons["randomize-methods"]
                    XCTAssertTrue(randomize.waitForExistence(timeout: 5)); randomize.click()
                    // AppKit can reorder the rows before the switch animations finish.
                    // Capture only once the visible selected rows form the leading group.
                    let toggles = app.switches.count > 0 ? app.switches : app.checkBoxes
                    let settled = NSPredicate { _, _ in
                        let values = toggles.allElementsBoundByIndex.map { String(describing: $0.value ?? "") }
                        guard !values.isEmpty, values.contains("1"), values.allSatisfy({ $0 == "0" || $0 == "1" }) else { return false }
                        var unchecked = false
                        for value in values {
                            if value == "0" { unchecked = true }
                            else if unchecked { return false }
                        }
                        return true
                    }
                    expectation(for: settled, evaluatedWith: app)
                    waitForExpectations(timeout: 10)
                    let randomShot = XCTAttachment(screenshot: window.screenshot())
                    randomShot.name = "macOS-\(theme)-random-methods"; randomShot.lifetime = .keepAlways; add(randomShot)
                }
            }
            XCTAssertTrue(app.staticTexts["vpn-status"].waitForExistence(timeout: 5))
            let resized = XCTAttachment(screenshot: window.screenshot())
            resized.name = "macOS-\(theme)-resized-fixture"; resized.lifetime = .keepAlways; add(resized)
            app.terminate()
        }
    }
}
