# FAQ presentation and traffic-mode explanations

Windows 0.25.0 → 0.25.1 (React/native/package versions together).
Android 0.21.0 / code 39 → 0.21.1 / code 40.
Public website 0.2.1 → 0.2.2. Backend 0.32.0 unchanged.

The owner confirmed this task applies to both clients and the public website.
Client dropdowns and the site's native details/summary accordion retain their
existing navigation and keyboard behavior.

## Behavior

- `FAQ` keeps uppercase letters, with a larger heading.
- A two-unit Purple Heart outline encloses the entire question selector. Android
  uses the native outlined button and existing dropdown; Windows keeps its native
  HTML select and keyboard behavior.
- Only meaningful links remain, inside answer sentences. Windows uses Router
  links and an inline support button; Android uses Compose LinkAnnotation with
  the same existing native navigation callbacks. No browser is opened.
- Translation strings mark link labels with brackets. They are rendered as text,
  never interpreted as HTML or arbitrary URLs. Each question owns its fixed target.
- The Free explanation has no unrelated subscription link. Cancellation copy is
  conditional on automatic renewal actually being enabled; it does not promise an
  active recurring payment integration.
- All six languages explain the three traffic modes with examples, exact domains
  versus wildcard subdomains, presets covering several domains, separate lists,
  and reconnecting after saving changes. This changes explanations only, not routing.
- The site's FAQ has a full rounded Purple Heart frame and a large uppercase
  heading. Download, payment-rules and support links appear inside relevant
  sentences. In-app home references remain plain text on the website to avoid
  misleading navigation. Destinations are fixed in code and all text is escaped.

## Checks and handoff

Updated existing interaction tests cover the heading, selection, inline link
placement, Free without links, both split directions and support navigation.
Website checks cover all six languages, answer paragraphs, inline links and route
resolution. Website publication uses a checked CI artifact on the existing main
server; it does not change backend configuration or activate payment processing.
Windows native review checks computed heading casing and border width, captures
the new split answer and follows the real subscription link. Android emulator
acceptance checks the new text, captures Free/split answers and taps the embedded
subscription link at its measured text position.

Run Windows formatting, types, lint, tests/build and Android language consistency,
build/unit/lint/emulator checks. Local Android SDK is unavailable; the existing CI
builds and tests the exact source on Android API 26/35/36. No real payment or new
VPN transport test is needed for this presentation-only change.

Final source HEAD, push/PR/reusable workflows, actual build SHA/run/attempt,
artifact/download links and inspected native screenshots are recorded in PR50
after the complete CI audit. Do not claim these changed screens were tested using
an older APK/installer. Client publishing is a separate operation from code push.

Cardlink credential retrieval is independent. The authenticated in-app browser's
API page says a token is only available after at least one shop passes moderation.
No API token has been retrieved or saved; no browser security check was bypassed.
