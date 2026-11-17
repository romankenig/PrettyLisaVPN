# Website plan emoji and language flags — 0.6.4

Owner follow-up on 2026-11-17. Public website 0.6.3 → 0.6.4 (PATCH for small
visual changes); backend and all client versions are unchanged. Base: develop
`3c592d6eecc4dbfb70af8cec0135e4c293a8c775` after PR #101.

The account's current-plan badge and summary use the same emoji as the clients and homepage:
Platinum 💎, Premium ⭐, Free 🕊️, Demo ⏳. Unknown plan labels remain plain text.
The backend plan value, entitlements, prices, renewal and payment behavior are
unchanged. The shared account template applies in every supported language.

The language selector replaces its generic symbol with an 18px local flag and
shows flags for all six options: ru/RU, en/GB, de/DE, fr/FR, es/ES and zh/CN.
The build copies the existing Chrome SVGs and MIT notice into `/assets/flags/`.
The website workflow watches these source assets. Decorative images have empty
alt text; language names, keyboard behavior and contextual links are preserved.
No external asset service, browser-language detection or new dependency is added.

Verification: existing Node checks/tests and 96-page build, changed JavaScript/
JSON formatting, diff review, desktop/mobile browser review and the existing
six-language account/browser acceptance. Caddy routing runs in isolated CI.
Final source/build SHA, run/attempt, artifact IDs, all CI jobs and any authorized
publication evidence are recorded in the task PR after the final push. No backend
follow-up or native client rebuild is required by the implementation.
