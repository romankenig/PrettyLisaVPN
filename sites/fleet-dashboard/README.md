# PrettyLisaVPN monitoring dashboard — 0.1.0

Standalone read-only React dashboard at `/dashboard/` on the main server.
The scheduler, probes, history and acceptance timer run independently of this UI.
No ChatGPT account, Sites runtime or browser polling is required for monitoring.

Build with `npm ci` and `npm run build` in this directory. The `dist/` artifact
contains no credentials. `install.py <dist.tar.gz> <source-sha>` installs it on the
main server and generates a random password on first use. Subsequent installations
preserve that login. Caddy validates the generated route before it is installed.

The deployment Caddyfile imports the optional operator-managed `dashboard/*.caddy`
route. Both assets and `/dashboard/api/availability` require HTTP Basic credentials
over HTTPS. The proxy substitutes a read-only backend monitoring token; that token
and the password hash never enter JavaScript or repository files. The operator's
login is kept in `/opt/prettylisavpn/secrets/dashboard/login.json` (mode 0600).
Keep this directory across releases; do not place it in CI artifacts.

The generic OTP login of VPN customers is unchanged. This password protects only
the administrative monitoring dashboard. Unknown/missing history remains unknown;
the dashboard shows coverage separately from successful known hours.
