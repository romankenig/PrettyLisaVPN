# Public payment return and support addresses

| Page | URL | Purpose |
| --- | --- | --- |
| Successful payment return | https://prettylisavpn.com/payment/success | Directs the customer to the subscription screen to check server-confirmed status. |
| Unsuccessful payment return | https://prettylisavpn.com/payment/failure | Directs the customer to check status before retrying. |
| Support | https://prettylisavpn.com/support | Opens the mail application for help@prettylisavpn.com. |

These pages are provider-independent. They never grant paid access or create a
payment. The billing provider remains disabled. There is no public payment callback
or merchant verification file. A future provider requires a separately tested
adapter, authenticated notifications and authoritative settlement.

The pages and their CSS/logo ship inside the backend image. Caddy exposes only
these paths on prettylisavpn.com; other paths return 404. Private monitoring remains
on api.prettylisavpn.com. Apex DNS points to 95.140.152.42. No Codex hosting or
scheduler is used. Return query strings are neither reflected nor logged by the
public-host configuration. Pages have CSP, no-referrer, no-store, noindex, and no
external scripts or trackers. `/support/` is also accepted; no form submission or
automatic email is performed.

## Compatibility and validation

Backend 0.31.0 removes the discontinued provider's callback and verification route.
See [removal handoff](payment-provider-removal.md). Schema remains 0041; the general
billing API, paid entitlements and clients are unchanged. Tests cover static pages,
assets, forged payment claims, removed routes returning 404 and private-path
isolation. Old release configurations must not be restored without this removal.
