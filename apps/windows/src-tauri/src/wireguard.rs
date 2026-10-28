//! Manage the separately installed official WireGuard client. No driver is bundled.
//! Only our fixed tunnel name is writable; private keys never leave this module.
use serde::Deserialize;
use std::{
    ffi::OsStr,
    fs::{self, OpenOptions},
    io::Write,
    net::{IpAddr, Ipv4Addr, SocketAddr, UdpSocket},
    os::windows::{ffi::OsStrExt, process::CommandExt},
    path::PathBuf,
    process::{Command, Stdio},
    sync::Mutex,
    time::Duration,
};
use tauri::{AppHandle, Manager};
use tauri_plugin_http::reqwest::{redirect::Policy, Client};
use windows_sys::Win32::{
    Foundation::{CloseHandle, GetLastError, ERROR_SERVICE_DOES_NOT_EXIST},
    System::{
        Services::*,
        Threading::{GetExitCodeProcess, WaitForSingleObject},
    },
    UI::{
        Shell::{ShellExecuteExW, SEE_MASK_NOCLOSEPROCESS, SHELLEXECUTEINFOW},
        WindowsAndMessaging::SW_HIDE,
    },
};
use zeroize::Zeroizing;

const NAME: &str = "PrettyLisaVPN";
const SERVICE: &str = "WireGuardTunnel$PrettyLisaVPN";
const HOST: &str = "api.prettylisavpn.com";
const FAILED: &str = "WIREGUARD_UNAVAILABLE";
const NO_WINDOW: u32 = 0x08000000;

#[derive(Default)]
pub struct WireGuardState {
    key: Mutex<Option<Zeroizing<String>>>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Configuration {
    address: String,
    server_public_key: String,
    endpoint: String,
    mtu: u16,
}

fn wide(value: impl AsRef<OsStr>) -> Vec<u16> {
    value.as_ref().encode_wide().chain(Some(0)).collect()
}
fn system(name: &str) -> PathBuf {
    PathBuf::from(std::env::var_os("SystemRoot").unwrap_or_else(|| "C:\\Windows".into()))
        .join("System32")
        .join(name)
}
fn installed(name: &str) -> Result<PathBuf, &'static str> {
    let path = PathBuf::from(std::env::var_os("ProgramFiles").ok_or(FAILED)?)
        .join("WireGuard")
        .join(name);
    if !path.is_file() {
        return Err("WIREGUARD_NOT_INSTALLED");
    }
    Ok(path)
}
fn command(program: PathBuf) -> Command {
    let mut command = Command::new(program);
    command.creation_flags(NO_WINDOW);
    command
}

fn service_state() -> Result<Option<u32>, &'static str> {
    unsafe {
        let manager = OpenSCManagerW(std::ptr::null(), std::ptr::null(), SC_MANAGER_CONNECT);
        if manager.is_null() {
            return Err(FAILED);
        }
        let service = OpenServiceW(manager, wide(SERVICE).as_ptr(), SERVICE_QUERY_STATUS);
        if service.is_null() {
            let error = GetLastError();
            CloseServiceHandle(manager);
            return if error == ERROR_SERVICE_DOES_NOT_EXIST {
                Ok(None)
            } else {
                Err(FAILED)
            };
        }
        let mut status: SERVICE_STATUS_PROCESS = std::mem::zeroed();
        let mut needed = 0;
        let ok = QueryServiceStatusEx(
            service,
            SC_STATUS_PROCESS_INFO,
            &mut status as *mut _ as *mut u8,
            std::mem::size_of_val(&status) as u32,
            &mut needed,
        );
        CloseServiceHandle(service);
        CloseServiceHandle(manager);
        if ok == 0 {
            Err(FAILED)
        } else {
            Ok(Some(status.dwCurrentState))
        }
    }
}

fn elevate(parameters: &str) -> Result<(), &'static str> {
    let file = wide(installed("wireguard.exe")?);
    let arguments = wide(parameters);
    let verb = wide("runas");
    unsafe {
        let mut info: SHELLEXECUTEINFOW = std::mem::zeroed();
        info.cbSize = std::mem::size_of_val(&info) as u32;
        info.fMask = SEE_MASK_NOCLOSEPROCESS;
        info.lpVerb = verb.as_ptr();
        info.lpFile = file.as_ptr();
        info.lpParameters = arguments.as_ptr();
        info.nShow = SW_HIDE;
        if ShellExecuteExW(&mut info) == 0 {
            return Err("VPN_ADMIN_PERMISSION_REQUIRED");
        }
        if info.hProcess.is_null() {
            return Err(FAILED);
        }
        let waited = WaitForSingleObject(info.hProcess, 30_000);
        let mut exit = 1;
        let result = GetExitCodeProcess(info.hProcess, &mut exit);
        CloseHandle(info.hProcess);
        if waited != 0 || result == 0 || exit != 0 {
            return Err(FAILED);
        }
    }
    Ok(())
}

fn config_path(app: &AppHandle) -> Result<PathBuf, &'static str> {
    Ok(app
        .path()
        .app_config_dir()
        .map_err(|_| FAILED)?
        .join("wireguard")
        .join(format!("{NAME}.conf")))
}
fn stop(app: &AppHandle) -> Result<(), &'static str> {
    if service_state()?.is_some() {
        elevate(&format!("/uninstalltunnelservice {NAME}"))?;
        // SCM deletion can finish after wireguard.exe exits. Do not mistake
        // that short transition for a permanently failed cleanup.
        let until = std::time::Instant::now() + Duration::from_secs(10);
        while service_state() != Ok(None) {
            if std::time::Instant::now() >= until {
                return Err("VPN_CLEANUP_FAILED");
            }
            std::thread::sleep(Duration::from_millis(100));
        }
    }
    let path = config_path(app)?;
    if path.exists() {
        fs::remove_file(path).map_err(|_| "VPN_CLEANUP_FAILED")?;
    }
    *app.state::<WireGuardState>()
        .key
        .lock()
        .map_err(|_| FAILED)? = None;
    Ok(())
}

fn preflight() -> Result<(), &'static str> {
    installed("wireguard.exe")?;
    // Read-only. In particular, never disable the user's Kaspersky tunnel.
    let script = "$ErrorActionPreference='Stop'; $r=Get-NetRoute -AddressFamily IPv4; if($r | Where-Object {$_.DestinationPrefix -in @('0.0.0.0/1','128.0.0.0/1')}) {exit 17}; $v=Get-NetAdapter | Where-Object {$_.InterfaceDescription -match 'WireGuard|Wintun|TAP|VPN|Kaspersky'}; if($r | Where-Object {$_.DestinationPrefix -eq '0.0.0.0/0' -and $_.InterfaceIndex -in $v.ifIndex}) {exit 17}";
    let status = command(system("WindowsPowerShell\\v1.0\\powershell.exe"))
        .args(["-NoProfile", "-NonInteractive", "-Command", script])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|_| FAILED)?;
    match status.code() {
        Some(0) => Ok(()),
        Some(17) => Err("VPN_CONFLICT"),
        _ => Err(FAILED),
    }
}

fn valid_key(key: &str) -> bool {
    key.len() == 44
        && key.ends_with('=')
        && key[..43]
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'+' || c == b'/')
}
fn prepare(app: &AppHandle) -> Result<String, &'static str> {
    preflight()?;
    if service_state()?.is_some() {
        return Err("VPN_CLEANUP_REQUIRED");
    }
    let generated = command(installed("wg.exe")?)
        .arg("genkey")
        .stderr(Stdio::null())
        .output()
        .map_err(|_| FAILED)?;
    if !generated.status.success() {
        return Err(FAILED);
    }
    let key = Zeroizing::new(
        String::from_utf8(generated.stdout)
            .map_err(|_| FAILED)?
            .trim()
            .to_owned(),
    );
    if !valid_key(&key) {
        return Err(FAILED);
    }
    let mut child = command(installed("wg.exe")?)
        .arg("pubkey")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| FAILED)?;
    child
        .stdin
        .take()
        .ok_or(FAILED)?
        .write_all(key.as_bytes())
        .map_err(|_| FAILED)?;
    let output = child.wait_with_output().map_err(|_| FAILED)?;
    let public = String::from_utf8(output.stdout)
        .map_err(|_| FAILED)?
        .trim()
        .to_owned();
    if !output.status.success() || !valid_key(&public) {
        return Err(FAILED);
    }
    *app.state::<WireGuardState>()
        .key
        .lock()
        .map_err(|_| FAILED)? = Some(key);
    Ok(public)
}

fn validate(config: &Configuration) -> Result<Ipv4Addr, &'static str> {
    let address: Ipv4Addr = config
        .address
        .strip_suffix("/32")
        .ok_or(FAILED)?
        .parse()
        .map_err(|_| FAILED)?;
    let endpoint: SocketAddr = config.endpoint.parse().map_err(|_| FAILED)?;
    if !address.is_private()
        || !endpoint.is_ipv4()
        || endpoint.port() < 1024
        || !valid_key(&config.server_public_key)
        || !(1280..=1420).contains(&config.mtu)
    {
        return Err(FAILED);
    }
    Ok(address)
}

fn start(app: &AppHandle, config: Configuration) -> Result<(), &'static str> {
    validate(&config)?;
    preflight()?;
    if service_state()?.is_some() {
        return Err("VPN_CLEANUP_REQUIRED");
    }
    let key = app
        .state::<WireGuardState>()
        .key
        .lock()
        .map_err(|_| FAILED)?
        .take()
        .ok_or(FAILED)?;
    let path = config_path(app)?;
    let directory = path.parent().ok_or(FAILED)?;
    fs::create_dir_all(directory).map_err(|_| FAILED)?;
    let user = command(system("whoami.exe"))
        .args(["/user", "/fo", "csv", "/nh"])
        .output()
        .map_err(|_| FAILED)?;
    let sid = String::from_utf8_lossy(&user.stdout)
        .split(',')
        .next_back()
        .ok_or(FAILED)?
        .trim()
        .trim_matches('"')
        .to_owned();
    if !sid.starts_with("S-1-5-")
        || !sid
            .bytes()
            .all(|c| c.is_ascii_digit() || c == b'-' || c == b'S')
    {
        return Err(FAILED);
    }
    let acl = command(system("icacls.exe"))
        .arg(directory)
        .args([
            "/inheritance:r",
            "/grant:r",
            &format!("*{sid}:(OI)(CI)F"),
            "*S-1-5-18:(OI)(CI)F",
            "*S-1-5-32-544:(OI)(CI)F",
        ])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()
        .map_err(|_| FAILED)?;
    if !acl.success() {
        return Err(FAILED);
    }
    let text = Zeroizing::new(format!("[Interface]\nPrivateKey = {}\nAddress = {}\nDNS = 1.1.1.1, 9.9.9.9\nMTU = {}\n[Peer]\nPublicKey = {}\nEndpoint = {}\nAllowedIPs = 0.0.0.0/0, ::/0\nPersistentKeepalive = 25\n", key.as_str(), config.address, config.mtu, config.server_public_key, config.endpoint));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&path)
        .map_err(|_| FAILED)?;
    file.write_all(text.as_bytes()).map_err(|_| FAILED)?;
    file.sync_all().map_err(|_| FAILED)?;
    drop(file);
    elevate(&format!("/installtunnelservice \"{}\"", path.display()))?;
    Ok(())
}

// Fixed health hostname, random transaction, bound source: no OS resolver/cache or fallback route.
fn resolve(address: Ipv4Addr) -> Result<Ipv4Addr, &'static str> {
    let socket = UdpSocket::bind((address, 0)).map_err(|_| "VPN_DNS_FAILED")?;
    socket
        .set_read_timeout(Some(Duration::from_secs(8)))
        .map_err(|_| FAILED)?;
    socket
        .connect((Ipv4Addr::new(1, 1, 1, 1), 53))
        .map_err(|_| "VPN_DNS_FAILED")?;
    let id = uuid::Uuid::new_v4().as_bytes()[..2].to_vec();
    let mut query = vec![id[0], id[1], 1, 0, 0, 1, 0, 0, 0, 0, 0, 0];
    for label in HOST.split('.') {
        query.push(label.len() as u8);
        query.extend(label.bytes());
    }
    query.extend([0, 0, 1, 0, 1]);
    socket.send(&query).map_err(|_| "VPN_DNS_FAILED")?;
    let mut bytes = [0u8; 4096];
    let size = socket.recv(&mut bytes).map_err(|_| "VPN_DNS_FAILED")?;
    dns_answer(&bytes[..size], [id[0], id[1]])
}
fn skip_name(data: &[u8], cursor: &mut usize) -> Result<(), &'static str> {
    for _ in 0..128 {
        let len = *data.get(*cursor).ok_or("VPN_DNS_FAILED")? as usize;
        *cursor += 1;
        if len == 0 {
            return Ok(());
        }
        if len & 0xc0 == 0xc0 {
            *cursor += 1;
            return if *cursor <= data.len() {
                Ok(())
            } else {
                Err("VPN_DNS_FAILED")
            };
        }
        if len > 63 {
            break;
        }
        *cursor += len;
    }
    Err("VPN_DNS_FAILED")
}
fn dns_answer(data: &[u8], id: [u8; 2]) -> Result<Ipv4Addr, &'static str> {
    if data.len() < 12
        || data[..2] != id
        || data[2] & 0x82 != 0x80
        || data[3] & 15 != 0
        || data[4..6] != [0, 1]
    {
        return Err("VPN_DNS_FAILED");
    }
    let mut cursor = 12;
    skip_name(data, &mut cursor)?;
    cursor += 4;
    let answers = u16::from_be_bytes([data[6], data[7]]);
    for _ in 0..answers {
        skip_name(data, &mut cursor)?;
        let head = data.get(cursor..cursor + 10).ok_or("VPN_DNS_FAILED")?;
        let length = u16::from_be_bytes([head[8], head[9]]) as usize;
        cursor += 10;
        let value = data.get(cursor..cursor + length).ok_or("VPN_DNS_FAILED")?;
        if head[..4] == [0, 1, 0, 1] && length == 4 {
            return Ok(Ipv4Addr::new(value[0], value[1], value[2], value[3]));
        }
        cursor += length;
    }
    Err("VPN_DNS_FAILED")
}

#[tauri::command]
pub async fn wg_prepare(app: AppHandle) -> Result<String, &'static str> {
    tauri::async_runtime::spawn_blocking(move || prepare(&app))
        .await
        .map_err(|_| FAILED)?
}
#[tauri::command]
pub async fn wg_start(app: AppHandle, configuration: Configuration) -> Result<(), &'static str> {
    tauri::async_runtime::spawn_blocking(move || start(&app, configuration))
        .await
        .map_err(|_| FAILED)?
}
#[tauri::command]
pub async fn wg_stop(app: AppHandle) -> Result<(), &'static str> {
    tauri::async_runtime::spawn_blocking(move || stop(&app))
        .await
        .map_err(|_| FAILED)?
}
#[tauri::command]
pub async fn wg_is_up() -> Result<bool, &'static str> {
    tauri::async_runtime::spawn_blocking(|| {
        service_state().map(|state| state == Some(SERVICE_RUNNING))
    })
    .await
    .map_err(|_| FAILED)?
}
#[tauri::command]
pub async fn wg_verify(
    address: String,
    session_id: String,
    access_token: String,
) -> Result<bool, &'static str> {
    let local: Ipv4Addr = address
        .strip_suffix("/32")
        .ok_or(FAILED)?
        .parse()
        .map_err(|_| FAILED)?;
    if !local.is_private() {
        return Err(FAILED);
    }
    let identifier = uuid::Uuid::parse_str(&session_id).map_err(|_| FAILED)?;
    if service_state()? != Some(SERVICE_RUNNING) {
        return Err(FAILED);
    }
    let resolved = tauri::async_runtime::spawn_blocking(move || resolve(local))
        .await
        .map_err(|_| FAILED)??;
    let client = Client::builder()
        .local_address(IpAddr::V4(local))
        .resolve(HOST, SocketAddr::new(IpAddr::V4(resolved), 443))
        .no_proxy()
        .redirect(Policy::none())
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|_| FAILED)?;
    let token = Zeroizing::new(access_token);
    let mut response = client
        .get(format!(
            "https://{HOST}/vpn/wireguard/sessions/{identifier}/probe"
        ))
        .bearer_auth(token.as_str())
        .header("Cache-Control", "no-store")
        .send()
        .await
        .map_err(|_| "VPN_HTTPS_FAILED")?;
    if !response.status().is_success() {
        return Err("VPN_HTTPS_FAILED");
    }
    let mut body = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| FAILED)? {
        if body.len() + chunk.len() > 4096 {
            return Err(FAILED);
        }
        body.extend(chunk);
    }
    let result: serde_json::Value = serde_json::from_slice(&body).map_err(|_| FAILED)?;
    Ok(result["verified"].as_bool() == Some(true))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_configuration_injection_and_non_tunnel_addresses() {
        let mut config = Configuration {
            address: "10.88.1.2/32".into(),
            server_public_key: "A".repeat(43) + "=",
            endpoint: "5.181.49.183:51820".into(),
            mtu: 1380,
        };
        assert!(validate(&config).is_ok());
        for address in ["127.0.0.1/32", "10.88.1.2/24", "10.88.1.2/32\nPostUp=x"] {
            config.address = address.into();
            assert!(validate(&config).is_err());
        }
        assert!(!valid_key("bad\nkey"));
    }
    #[test]
    fn rejects_truncated_unrelated_and_compressed_dns_loops() {
        for data in [
            vec![],
            vec![0; 12],
            vec![1, 2, 0x80, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0xc0],
        ] {
            assert!(dns_answer(&data, [1, 2]).is_err());
        }
    }
}
