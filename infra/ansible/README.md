# Infrastructure after the VPN reset

The previous node-agent, WireGuard, OpenVPN, profile and obfuscator roles/playbooks
have been removed. No replacement VPN server is provisioned in this task.

The pre-reset source is preserved in merge commit
`dc3789904cb903eb100b9e35a3bea436146a753a` (PR #29).
See [the reset handoff](../../docs/vpn-placeholder-reset.md) for decommissioning
evidence and rollback boundaries. SSH and the account backend are separate services.
