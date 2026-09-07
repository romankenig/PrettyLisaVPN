# PrettyLisaVPN Repository Guidelines

## Product Context

PrettyLisaVPN is a multi-platform commercial VPN service.

Supported client platforms:

- Windows
- macOS
- Linux
- Android
- iOS
- Android TV
- Chrome Extension

The Chrome Extension is browser-only. It must use a proxy-based implementation rather than a system-wide WireGuard tunnel.

## Product Requirements

- Authentication is passwordless and uses email OTPs.
- Free users receive 15-minute Autopilot VPN sessions.
- After a free session expires, the user must complete a rewarded-ad flow before starting another 15-minute session.
- Premium users have no ads and no 15-minute session limit.
- Premium users can explicitly select a VPN server country.
- Split tunneling must eventually support both whitelist and blacklist modes. Do not implement this future capability unless the current task requires it.
- Each account may have up to five active devices.
- Payments and recurring subscriptions use external payment providers such as ЮКасса.
- Support product and acquisition analytics without collecting or logging users' browsing history.

## Architecture

- Start the Backend as a modular monolith, not microservices.
- Use Python 3.13 and FastAPI.
- PostgreSQL is the source of truth for persistent business data.
- Use Redis only for ephemeral concerns such as OTPs, caching, locks, rate limits, and short-lived sessions.
- Use SQLAlchemy 2.x for persistence.
- Use Alembic for database migrations.
- Use Pydantic v2 for API schemas and configuration.
- Integrate external services through ports/adapters or provider interfaces. Providers must be replaceable and mockable.
- Keep business logic out of HTTP controllers. Controllers should validate and translate transport concerns, then delegate to application/domain services.
- WireGuard is the primary system-wide VPN protocol.
- Keep the VPN control plane and VPN data plane separate.
- User VPN traffic must never pass through the Backend API.
- Manage infrastructure with Terraform and Ansible.
- Use Docker for local development and deployment packaging.
- Avoid Kubernetes for the MVP unless explicitly requested.
- Prefer simple, concrete solutions over speculative abstractions.
- Do not implement future roadmap items unless required by the current task.

## Data, Privacy, and Security

- Do not collect or log browsing history.
- Never log browsing destinations, DNS queries, URLs, or packet contents.
- Never log OTP values in production.
- Never log WireGuard private keys.
- Never commit secrets. Keep `.env.example` synchronized with required configuration using safe placeholder values.
- Never store raw payment-card details. Payment data must be handled by external payment providers.
- Use structured logging.
- Use UTC timestamps internally.
- Use UUIDs for externally exposed IDs unless there is a strong documented reason not to.
- API errors must expose stable, machine-readable error codes.

## Engineering Rules

- Inspect the repository and its existing conventions before editing.
- Do not rewrite or reformat unrelated code.
- Preserve backwards compatibility unless the task explicitly requires a breaking change.
- Reuse existing tooling and dependencies when they already solve the requirement.
- For client UI work, follow the shared logo and color rules in `docs/design-system.md`.
- Every database schema change requires an Alembic migration.
- Every new endpoint requires tests.
- Every business rule requires unit tests.
- Add integration tests when behavior crosses module or infrastructure boundaries.
- External providers must be mockable in tests.
- Run the relevant formatting, linting, type-checking, and test commands before finishing.
- After completing and verifying changes, commit them and push the current branch to `origin` so the remote repository stays synchronized, unless the user explicitly says not to push.

## Task Workflow

For every coding task:

1. Inspect the relevant files and existing conventions.
2. Briefly state the implementation plan.
3. Implement the smallest coherent solution.
4. Add or update tests.
5. Run the relevant formatting, linting, type-checking, and test commands.
6. Review the diff for security, correctness, backwards compatibility, and unrelated changes.
7. Commit the verified changes and push the current branch to `origin`, unless explicitly instructed not to push.
8. Summarize:
   - files changed;
   - architecture decisions;
   - tests and checks run;
   - remaining risks or follow-up work.
