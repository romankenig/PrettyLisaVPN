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

The native commands are:

- `start_wireguard_tunnel`: validates endpoint, server public key, client CIDR, DNS servers and
  AllowedIPs; reads the client private key from Windows Credential Manager; configures and starts
  the adapter.
- `stop_wireguard_tunnel`: brings down and releases the active adapter; repeated calls are safe.
- `get_wireguard_tunnel_state`: reports `UP` or `DOWN` from the live native adapter.

The active adapter handle is process-local. A normal stop or process exit releases the adapter and
Windows removes its routes and DNS state. The client private key remains protected by Windows
Credential Manager for reuse, but is never returned over Tauri IPC, passed to `netsh`, logged, or
written to a configuration file.

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
