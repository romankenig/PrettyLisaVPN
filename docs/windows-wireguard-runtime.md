# Windows WireGuard runtime

PrettyLisaVPN controls a WireGuardNT adapter directly from its Tauri Rust process. It does not
install, automate, or require the WireGuard GUI. Tunnel configuration is passed as typed values to
the driver API in memory; no WireGuard `.conf` file is created.

## Components

- `wireguard.dll`: the official, Microsoft-signed WireGuardNT prebuilt library/driver package from
  <https://download.wireguard.com/wireguard-nt/>. The x64 DLL must be placed beside
  `prettylisavpn-windows.exe` for the currently supported x64 build.
- `wireguard-nt` Rust crate: MIT-licensed bindings that dynamically load the DLL by an absolute
  path and expose the WireGuardNT adapter API.
- Windows IP Helper APIs, used by the binding for interface addresses and routes.
- Windows `netsh.exe`, invoked directly with separate arguments to set adapter DNS. It is never
  invoked through a shell and never receives key material.

The repository intentionally does not silently download or commit a native binary. The release
pipeline must pin a reviewed WireGuardNT release and SHA-256 digest, verify the Authenticode
signature, and stage both the architecture-matched `wireguard.dll` and its exact accompanying
`LICENSE.txt` beside the signed PrettyLisaVPN executable before packaging.

Example release preparation after downloading the official WireGuardNT archive to a trusted build
workspace:

```powershell
Get-AuthenticodeSignature .\wireguard.dll | Format-List Status,SignerCertificate
Get-FileHash .\wireguard.dll -Algorithm SHA256
Copy-Item .\wireguard.dll .\release\wireguard.dll
Copy-Item .\LICENSE.txt .\release\LICENSE.wireguard-nt.txt
```

Fail the release if the signature is not valid or the hash differs from the version pinned in the
release manifest. Do not substitute a same-named DLL from another source.

## Privileges and lifecycle

Creating a Windows network adapter, assigning routes/DNS, and loading the WireGuardNT driver
requires administrator rights. The Windows application manifest requests
`requireAdministrator` in release builds, so Windows presents a normal UAC consent prompt when
PrettyLisaVPN starts. Debug/test artifacts omit that manifest so unit tests remain unattended;
developers must launch `pnpm tauri dev` from an elevated terminal when exercising a real tunnel.
The user is not asked to install or configure another application. A future least-privilege split
between the UI and a signed privileged service can preserve the same Rust tunnel interface, but is
not introduced here.

## Packet transport selection

The native runtime supports two deliberately small modes selected before starting the process:

- `DIRECT` (default): WireGuardNT uses the Backend-provided public endpoint directly. This remains
  available for diagnostics and nodes that intentionally expose raw WireGuard.
- `PRETTYLISA_V1`: a process-local Rust UDP relay binds an ephemeral `127.0.0.1` port. WireGuardNT
  uses that localhost endpoint, while the relay applies the exact Stage 3AB version-1
  ChaCha20-Poly1305 envelope and sends it to the Backend-provided public endpoint.

Selection is native-only:

```text
PRETTYLISA_VPN_TRANSPORT_MODE=PRETTYLISA_V1
PRETTYLISA_V1_SECRET=<canonical Base64 encoding of 32 bytes>
PRETTYLISA_V1_PUBLIC_PORT=443
```

The secret is never passed through React, Tauri IPC, the WireGuard configuration, diagnostics, or
logs. For Stage 3AC it is supplied to the process environment during a controlled test. Durable
client provisioning and rotation are not introduced in this stage.

The Backend endpoint continues to describe the node's raw WireGuard listener because node health
validates that port against `wg0`. In V1 mode the relay preserves the selected node IP but replaces
that internal port with `PRETTYLISA_V1_PUBLIC_PORT` (UDP/443 by default). The route lifecycle creates
the selected node's public `/32` bypass through the physical gateway. The WireGuard peer endpoint is
localhost, but the bypass is based on the real public node IP so the relay's encrypted UDP socket
cannot be captured by the full-tunnel routes.

The native commands are:

- `start_wireguard_tunnel`: validates endpoint, server public key, client CIDR, DNS servers and
  AllowedIPs; reads the client private key from Windows Credential Manager; configures and starts
  the adapter.
- `stop_wireguard_tunnel`: brings down and releases the active adapter; repeated calls are safe.
- `get_wireguard_tunnel_state`: reports `UP` or `DOWN` from the live native adapter.
- `get_wireguard_peer_diagnostics`: reports the live peer plus transport mode, transport health,
  public endpoint and byte counters, but never private keys or the obfuscation secret.

The active adapter handle is process-local. A normal stop or process exit releases the adapter and
Windows removes its routes and DNS state. The client private key remains protected by Windows
Credential Manager for reuse, but is never returned over Tauri IPC, passed to `netsh`, logged, or
written to a configuration file.

Disconnect, failed startup, handshake timeout, transport failure, and normal process exit all stop
WireGuard, remove transient routes, signal and join the relay thread, and close its sockets.

## Redistribution obligations

The official prebuilt `wireguard.dll` is governed by the **Prebuilt Binaries License** included in
its download, not merely by the source repository's GPL-2.0 license. In particular, distribute the
unmodified DLL only alongside software that uses the permitted `wireguard.h` API, retain all
notices, include the exact license text, do not reverse engineer or use WireGuard names for
endorsement, and obtain separate legal review before changing the distribution model. The Rust
binding is MIT licensed and its notice must remain in the application's third-party notices.

Upstream references:

- <https://www.wireguard.com/embedding/>
- <https://git.zx2c4.com/wireguard-nt/about/>
- <https://git.zx2c4.com/wireguard-nt/tree/prebuilt-binaries-license.txt>

## Verification

Run the application elevated with the reviewed DLL beside the executable, obtain a backend session
transport response, and start the native tunnel. In an elevated PowerShell window:

```powershell
Get-NetAdapter -Name PrettyLisaVPN
Get-NetIPAddress -InterfaceAlias PrettyLisaVPN
Get-NetRoute -InterfaceAlias PrettyLisaVPN
Get-DnsClientServerAddress -InterfaceAlias PrettyLisaVPN
```

The Tauri state command must report `UP`. After stop it must report `DOWN`, and the transient
adapter/routes must be absent. Neither the application directory nor `%APPDATA%` should contain a
WireGuard `.conf` file.

In `PRETTYLISA_V1`, the diagnostic peer endpoint must be `127.0.0.1:<ephemeral-port>`, transport
mode must be `PRETTYLISA_V1`, transport health must be true, and the public endpoint must remain the
selected node. `Get-NetRoute` must show the node's public `/32` through the physical interface.

### Stage 3AC manual V1 test

After Stage 3AB is deployed on the node, open PowerShell **as Administrator**. Capture the node
secret without printing it or writing it to disk, validate its size, and launch Tauri from the same
process:

```powershell
$Repo = "C:\Users\kenro\Desktop\main\PrettyLisaVPN"
$SshKey = Join-Path $Repo "keys\github-actions-development"
$prefix = "PRETTYLISA_OBFUSCATION_SECRET="
$secretLine = (& ssh.exe -i $SshKey vpnadmin@204.48.17.50 `
  "sudo cat /etc/prettylisavpn-obfuscator/secret.env").Trim()
if ($LASTEXITCODE -ne 0 -or -not $secretLine.StartsWith($prefix)) {
  throw "Unable to load the node obfuscation secret"
}
$secret = $secretLine.Substring($prefix.Length)
if ([Convert]::FromBase64String($secret).Length -ne 32) {
  throw "Invalid node obfuscation secret"
}
$env:PRETTYLISA_VPN_TRANSPORT_MODE = "PRETTYLISA_V1"
$env:PRETTYLISA_V1_SECRET = $secret
$env:PRETTYLISA_V1_PUBLIC_PORT = "443"
Set-Location (Join-Path $Repo "apps\windows")
pnpm tauri dev
```

After closing the application:

```powershell
Remove-Item Env:PRETTYLISA_V1_SECRET -ErrorAction SilentlyContinue
Remove-Item Env:PRETTYLISA_VPN_TRANSPORT_MODE -ErrorAction SilentlyContinue
Remove-Item Env:PRETTYLISA_V1_PUBLIC_PORT -ErrorAction SilentlyContinue
$secret = $null
$secretLine = $null
```

While connected, verify the physical `/32` bypass and local listener without showing secrets:

```powershell
Get-NetRoute -DestinationPrefix "204.48.17.50/32" |
  Format-Table DestinationPrefix,InterfaceAlias,NextHop,RouteMetric
Get-NetUDPEndpoint -OwningProcess (Get-Process prettylisavpn-windows).Id |
  Format-Table LocalAddress,LocalPort,OwningProcess
Get-NetAdapter -Name PrettyLisaVPN
Get-NetRoute -InterfaceAlias PrettyLisaVPN
```

In another SSH session, observe only interface/length metadata, never packet payload hex or ASCII:

```bash
sudo tcpdump -ni any -c 40 'udp port 443 or (udp port 51820 and host 127.0.0.1)'
sudo wg show wg0 latest-handshakes
sudo wg show wg0 transfer
```
