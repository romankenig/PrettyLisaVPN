# Pinned wg-obfuscator experiment (Windows + Ubuntu)

This is an explicit diagnostic transport, not a demonstrated fix for ISP filtering.
Modes remain `DIRECT`, `PRETTYLISA_V1`, and `WG_OBFUSCATOR`. Defaults are unchanged.
Use [ClusterM v1.6](https://github.com/ClusterM/wg-obfuscator/releases/tag/v1.6)
on both ends. No upstream protocol is reimplemented in Rust.

## Packet path and lifecycle

WireGuardNT (unchanged, AllowedIPs 0.0.0.0/0) → ephemeral 127.0.0.1 UDP socket
owned by the pinned Windows sidecar → selected node IPv4:443 → Linux sidecar →
127.0.0.1:51820 → wg0. Responses follow the reverse path.

The native process starts suspended, enters a kill-on-close Job Object, and is
resumed. Readiness requires its PID to own the exact localhost UDP socket. A bind
race, missing component, hash mismatch, failed job assignment or early exit aborts
startup before WireGuard/full-tunnel routes. stdout/stderr are suppressed; native
structured events report startup, readiness and exit without upstream packet dumps.
Only SystemRoot is inherited, not application credentials.

The existing endpoint /32 bypass still uses the **public** node IP, not loopback.
It is installed before adapter.up(): upstream does not initiate traffic before a
WireGuard datagram arrives. The existing handshake/data probe still gates Connected.
MTU remains 1280. No backend, selection policy or WireGuard keys change.

Normal disconnect stops WireGuard/removes routes, then kills/reaps the sidecar.
Failed setup drops the transport. Existing native state polling detects child exit
and cleans the active tunnel; detection is bounded by the application's polling,
not an independent watchdog. Job Object closes sidecar sockets if the parent dies.
This does not by itself prove Windows route/DNS restoration after arbitrary forced
termination of the entire app: retain that manual crash-recovery test.

## Security and packaging

This upstream obfuscator is **not** the PrettyLisa ChaCha20-Poly1305 envelope and
does not add an authenticated encryption guarantee. WireGuard authenticates and
encrypts the VPN traffic. Do not claim this is stronger cryptography or an
undetectable transport. A wrong obfuscation key should prevent a valid WG handshake;
WireGuard, not the obfuscator, is the authentication boundary.

Only `NONE` and explicit `STUN` are accepted; `AUTO` is intentionally not exposed.
No clean-client acceptance, timeout-triggered source-port rotation or TRACE logging.
v1.6 help differs from its parser: use verbosity `0`, not `ERRORS`; omit in-timeout
to use disabled default, because an explicit `--in-timeout 0` is rejected.

Server key is generated once at `/etc/prettylisavpn-wg-obfuscator/key.conf`, root:
plvpn-wg-obfuscator 0640 in a 0750 directory. Windows uses
`%LOCALAPPDATA%\PrettyLisaVPN\wg-obfuscator\key.conf`, ACL restricted to the user,
Administrators and SYSTEM. Contents must be exactly `key=` followed by 64 hex
characters (optional trailing whitespace). No private WireGuard key is involved.
Never use `--key`, VITE variables, Git or a transcript to transfer the secret.
The import script uses encrypted SSH and captures the secret without printing it.
This is a development machine credential; production distribution/rotation and
per-node transport settings remain separate deployment work.

Archive SHA256:

- Windows x64 ZIP: `2e940fcd137ad13e4ef881237c6ad5e08cb16de8415f5b2324ebca16393df04e`
- Linux x64 tar.gz: `af30264278c70c2e53ad3234e8050686b3bef4f6564edc9fb068ea8c885b8354`

Windows runtime independently verifies the EXE and both adjacent MSYS DLLs; see
`wg_obfuscator.rs` for their pinned digests. Do not relocate the EXE without the DLLs.
Upstream ships GPLv3 text. Before commercial redistribution, review obligations,
preserve notices and provide corresponding source/build material as required,
including the bundled MSYS/GCC runtime dependencies. A separate process is not a
blanket exemption from licensing obligations. No production installer is modified.

## Exact Ubuntu/WSL deploy and rollback

Existing key-only SSH, active UFW, WireGuard, NAT and original PrettyLisa V1 service
are prerequisites. Run from the repo in Ubuntu/WSL; use your existing private-key
path. This limit is mandatory for this experiment: Netcup remains unchanged.

```bash
cd /mnt/c/Users/kenro/Desktop/main/PrettyLisaVPN/infra/ansible
export ANSIBLE_CONFIG=ansible.cfg
ansible-playbook playbooks/wg-obfuscator.yml --syntax-check
ansible-playbook playbooks/wg-obfuscator.yml \
  --limit ubuntu-s-1vcpu-512mb-10gb-nyc1 \
  --private-key ~/.ssh/prettylisa-development -e wg_obfuscator_activate=false
# Switch only when ready to test Windows with the matching mode:
ansible-playbook playbooks/wg-obfuscator.yml \
  --limit ubuntu-s-1vcpu-512mb-10gb-nyc1 \
  --private-key ~/.ssh/prettylisa-development \
  -e wg_obfuscator_activate=true -e wg_obfuscator_masking=NONE
```

Activation stops/disables the original listener, starts/enables the new service,
then checks socket ownership. Startup failure restores the original service and
fails the play. This verifies startup only, **not end-to-end VPN connectivity**.
For the STUN experiment rerun the same activation command with
`-e wg_obfuscator_masking=STUN`, then start Windows with `-Masking STUN`.

On the node:

```bash
sudo systemctl restart prettylisavpn-wg-obfuscator
sudo systemctl is-active prettylisavpn-wg-obfuscator wg-quick@wg0
sudo systemctl is-enabled prettylisavpn-wg-obfuscator
sudo ss -H -lunp 'sport = :443'
sudo wg show wg0 listen-port
sudo ufw status verbose
sudo iptables -vnL ufw-user-input
sudo iptables -vnL ufw-user-forward
sudo iptables -t nat -vnL POSTROUTING
ip -4 route get 1.1.1.1
```

Expected UFW: trusted SSH preserved; public IPv4 UDP443 allowed; raw public UDP51820
not allowed; agent TCP8443 only from backend 95.140.152.42; narrow wg0→public NAT/
forwarding retained. DigitalOcean Cloud Firewall must also allow UDP443, not raw
51820. Kernel WireGuard can show a wildcard listener: firewall isolation, not a
claimed loopback bind, prevents public access. Do not expose DIRECT on this node
without a separate explicit diagnostic firewall change.

Manual reboot, only after a successful VPN test and at a suitable interruption:

```bash
sudo reboot
# Reconnect SSH, then repeat the status/listener/firewall checks above.
```

Rollback on the node (or DigitalOcean Recovery Console if SSH is unavailable):

```bash
sudo systemctl disable --now prettylisavpn-wg-obfuscator
sudo systemctl enable --now prettylisavpn-obfuscator
sudo ss -H -lunp 'sport = :443'
```

Restart Windows in `PRETTYLISA_V1` with its original secret, **not** the new hex key.
No database rollback or WireGuard key regeneration is needed.

## Exact Windows setup and controlled test

Run PowerShell 7 from the repository root. Component/key scripts do not start VPN.

```powershell
.\apps\windows\scripts\install-wg-obfuscator.ps1
.\apps\windows\scripts\import-wg-obfuscator-key.ps1 -SshIdentity .\keys\github-actions-development
.\apps\windows\scripts\dev-wg-obfuscator.ps1 -Masking NONE
```

Close any older development app first. Keep Kaspersky running while preparing.
The development launcher also supports Windows PowerShell 5.1: native stderr is
merged before entering the PowerShell pipeline, so pnpm progress messages are not
mistaken for terminating errors. Nonzero process exit codes still fail the launcher.
Regression check (no VPN or network is started):

```powershell
.\apps\windows\scripts\tests\test-dev-launcher.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\apps\windows\scripts\tests\test-dev-launcher.ps1
```

For the actual CONNECT test, **manually disconnect Kaspersky first**, then select
the US country (not Autopilot, which could pick unmodified Netcup), then CONNECT.
Native tunnel operation still requires the existing Windows elevation arrangement.
Watch `wg_obfuscator_ready`, readback endpoint 127.0.0.1, `transport_mode=WgObfuscator`,
AllowedIPs /0, handshake success and data-probe success.

From another PowerShell window after CONNECT:

```powershell
Get-NetRoute -DestinationPrefix '204.48.17.50/32'
Get-NetUDPEndpoint | Where-Object OwningProcess -in (Get-Process wg-obfuscator).Id
ping.exe -n 60 1.1.1.1
curl.exe --connect-timeout 10 --max-time 20 https://api.ipify.org
Resolve-DnsName example.com
```

Compare public IP with 204.48.17.50; run download/upload and leave the tunnel active
for 3–5 minutes. Disconnect twice, confirm no sidecar remains and the app-created
routes/DNS were restored; a pre-existing endpoint bypass must be preserved.
Test child crash by terminating **only the application's sidecar PID** and checking
the next state poll cleans the tunnel/backend session. Do not kill unrelated VPNs.

Server-side observation in parallel (metadata only, never `-A`, `-X`, `-w`):

```bash
sudo timeout 60 tcpdump -ni eth0 -q 'udp port 443'
sudo timeout 60 tcpdump -ni lo -q 'udp port 51820'
sudo wg show wg0 latest-handshakes
sudo wg show wg0 transfer
sudo iptables -t nat -vnL POSTROUTING
```

Determine the actual public interface with `ip -4 route get 1.1.1.1`; eth0 above is
the verified interface of this particular node. Avoid capturing wg0 user traffic
or DNS. On Windows, use a NIC capture filtered to node IPv4 + UDP443 if needed;
do not capture general user browsing. Socket sends do not prove NIC transmission.
Upstream mode does not expose relay packet counters: the snapshot is `None`, not
fabricated zero traffic (`counters_available=false`). WireGuardNT TX/RX remain available.

Repeat on the same node and UDP443: A original V1, B wg-obfuscator NONE, C STUN.
Record handshake, sustained bidirectional bytes, DNS, IP, cleanup and timestamps.
B working does not prove DPI; C-only success strengthens, but does not establish,
the masking hypothesis. Both failing requires simultaneous outer-network captures.

## Automated checks

```powershell
cd apps\windows\src-tauri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
cargo test
$env:PRETTYLISA_WG_OBFUSCATOR_EXE = 'C:\Users\kenro\Desktop\main\PrettyLisaVPN\.tools\wg-obfuscator-1.6\wg-obfuscator\wg-obfuscator.exe'
cargo test upstream_roundtrip_lifecycle_and_failure_cleanup -- --ignored --nocapture
cd ..
pnpm lint
pnpm typecheck
pnpm test -- src/test/wireguardTunnel.test.ts src/test/vpnConnection.test.ts
```

The explicit upstream test uses synthetic handshake-shaped datagrams and a dummy
key, not live WireGuard identities or production peers. It verifies real upstream
encode/decode in both modes, socket ownership, stop/drop cleanup and child crash.
It also checks rejection with a wrong obfuscation key; that is not an AEAD guarantee.
It does not prove a production WireGuard handshake, Internet reachability or DPI
evasion. Credential Manager tests require a normal Windows user logon session.

## Implementation/deployment report

The deployment installed v1.6 on DigitalOcean and activated NONE on UDP443.
Verified after cutover: new service active/enabled, old service inactive, wg0 and
Node Agent active, NRestarts=0, key.conf 0640 root:plvpn-wg-obfuscator, UFW logging
off and unchanged ingress/forward rules. No WireGuard keys were changed, no peers
added, no backend/DB changes, no Netcup changes and no Kaspersky state changes.
The original service and secret remain available for rollback.

Checks completed: 27 Rust tests passed (the component integration test is explicitly
opt-in and also passed separately), 25 focused TypeScript tests passed, cargo fmt,
clippy with warnings denied, frontend format/lint/typecheck, PowerShell syntax and
Ansible syntax/deploy passed. The opt-in test exercised NONE, STUN, wrong-key
rejection, duplicate stop, drop cleanup and process death. A pre-existing V1 test
counter race was fixed by joining the worker before reading the final snapshot.

Changed files:

- `apps/windows/src-tauri/src/wg_obfuscator.rs`: lifecycle, pinned components, validation, tests.
- `apps/windows/src-tauri/src/obfuscation_transport.rs`: mode integration and optional counters.
- `apps/windows/src-tauri/src/main.rs`: native module registration.
- `apps/windows/src-tauri/Cargo.toml`, `Cargo.lock`: SHA256 and Windows job/thread APIs.
- `apps/windows/src/native/wireguardTransport.ts`: native diagnostics type.
- `apps/windows/src/test/wireguardTunnel.test.ts`: both obfuscated modes covered.
- `apps/windows/.env.example`: safe native settings examples.
- `apps/windows/scripts/install-wg-obfuscator.ps1`: checksum-verified component installer.
- `apps/windows/scripts/import-wg-obfuscator-key.ps1`: SSH import to protected external storage.
- `apps/windows/scripts/dev-wg-obfuscator.ps1`: explicit development launcher/log file.
- `infra/ansible/playbooks/wg-obfuscator.yml`: node deployment entry point.
- `infra/ansible/roles/wg_obfuscator/defaults/main.yml`: explicit staging/masking settings.
- `infra/ansible/roles/wg_obfuscator/tasks/main.yml`: install, protected key, activation/rollback.
- `infra/ansible/roles/wg_obfuscator/templates/service.j2`: restricted service.
- `docs/wg-obfuscator.md`: protocol boundary, deployment, tests, rollback and limitations.

Still required before claiming the user's Internet problem fixed: actual Windows
CONNECT without Kaspersky, sustained Internet/DNS checks, A/B/C comparison on the
same public endpoint and manual reboot/crash recovery validation. Automated
localhost success alone cannot establish ISP filtering or its circumvention.
