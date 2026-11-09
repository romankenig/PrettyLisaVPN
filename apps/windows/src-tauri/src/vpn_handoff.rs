//! Only the separately installed, signed Kaspersky VPN product can be handed off.
use std::{
    os::windows::process::CommandExt,
    path::PathBuf,
    process::{Command, Stdio},
    time::{Duration, Instant},
};
const SCRIPT: &str = include_str!("vpn_handoff.ps1");
fn system(name: &str) -> PathBuf {
    PathBuf::from(std::env::var_os("SystemRoot").unwrap_or_else(|| "C:\\Windows".into()))
        .join("System32")
        .join(name)
}
fn bounded(mut command: Command, timeout: Duration) -> Result<(), &'static str> {
    let mut child = command
        .creation_flags(0x08000000)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| "VPN_CONFLICT")?;
    let until = Instant::now() + timeout;
    loop {
        if let Some(status) = child.try_wait().map_err(|_| "VPN_CONFLICT")? {
            return if status.success() {
                Ok(())
            } else {
                Err("VPN_CONFLICT")
            };
        }
        if Instant::now() >= until {
            let _ = child.kill();
            let _ = child.wait();
            return Err("VPN_CONFLICT");
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}
#[tauri::command]
pub async fn vpn_handoff() -> Result<(), &'static str> {
    tauri::async_runtime::spawn_blocking(|| {
        let mut command = Command::new(system("WindowsPowerShell\\v1.0\\powershell.exe"));
        command.args(["-NoProfile", "-NonInteractive", "-Command", SCRIPT]);
        bounded(command, Duration::from_secs(25))?;
        super::wireguard::route_preflight()
    })
    .await
    .map_err(|_| "VPN_CONFLICT")?
}
pub(super) fn flush_dns() -> Result<(), &'static str> {
    let mut command = Command::new(system("ipconfig.exe"));
    command.arg("/flushdns");
    bounded(command, Duration::from_secs(5)).map_err(|_| "VPN_DNS_CACHE_FAILED")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn handoff_only_exits_a_signed_separate_vpn_and_fails_closed() {
        // Execute the actual PowerShell policy with mocked OS boundaries. Never
        // enumerate, stop or launch any real VPN/antivirus during this test.
        let mocks = r#"
$script:active = $true
function Get-NetAdapter { [pscustomobject]@{Status='Up'; InterfaceDescription='Kaspersky VPN WG Nt Adapter Tunnel'; ifIndex=58} }
function Get-NetRoute { if ($script:active) { [pscustomobject]@{DestinationPrefix='0.0.0.0/1';InterfaceIndex=58} } }
function Test-Path { param($LiteralPath) return $LiteralPath.Contains('(x86)') }
function Get-ChildItem { param($LiteralPath, [switch]$Directory) [pscustomobject]@{Name='PRODUCT';FullName=(Join-Path $LiteralPath 'PRODUCT')} }
function Get-AuthenticodeSignature { param($LiteralPath) [pscustomobject]@{Status='SIGNATURE';SignerCertificate=[pscustomobject]@{Subject='CN=AO Kaspersky Lab, O=AO Kaspersky Lab'}} }
function Start-Process {
 param($FilePath,$ArgumentList,$WindowStyle,[switch]$PassThru)
 if ($FilePath -notmatch 'Kaspersky Secure Connection 5.27\\avp.com$' -or $ArgumentList -ne 'EXIT' -or $WindowStyle -ne 'Hidden') {throw 'unsafe invocation'}
 $script:active=$false
 Write-Host 'VPN_EXIT'
 $process=[pscustomobject]@{ExitCode=0}
 $process | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {param($timeout) $true}
 return $process
}
"#;
        for (product, signature, exit, invoked) in [
            ("Kaspersky Secure Connection 5.27", "Valid", 0, true),
            ("Kaspersky Secure Connection 5.27", "NotSigned", 17, false),
            ("Kaspersky Anti-Virus 5.27", "Valid", 17, false),
        ] {
            let script = format!(
                "{}\n{}",
                mocks
                    .replace("PRODUCT", product)
                    .replace("SIGNATURE", signature),
                SCRIPT
            );
            let output = Command::new(system("WindowsPowerShell\\v1.0\\powershell.exe"))
                .creation_flags(0x08000000)
                .args(["-NoProfile", "-NonInteractive", "-Command", &script])
                .output()
                .unwrap();
            assert_eq!(
                output.status.code(),
                Some(exit),
                "policy case {product}/{signature}"
            );
            assert_eq!(
                String::from_utf8_lossy(&output.stdout).contains("VPN_EXIT"),
                invoked
            );
        }
    }
}
