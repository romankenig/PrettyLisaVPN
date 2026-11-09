//! WireGuard uses the installed PrettyLisaVPN service, just like the other methods.
//! Private keys are generated here and never enter the renderer or disk.
use base64::{engine::general_purpose::STANDARD, Engine};
use serde::Deserialize;
use std::{
    net::{IpAddr, Ipv4Addr, SocketAddr, UdpSocket},
    os::windows::process::CommandExt,
    path::PathBuf,
    process::{Command, Stdio},
    sync::Mutex,
    time::Duration,
};
use tauri::{AppHandle, Manager};
use tauri_plugin_http::reqwest::{redirect::Policy, Client};
use zeroize::Zeroizing;
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

fn system(name: &str) -> PathBuf {
    PathBuf::from(std::env::var_os("SystemRoot").unwrap_or_else(|| "C:\\Windows".into()))
        .join("System32")
        .join(name)
}
fn command(program: PathBuf) -> Command {
    let mut command = Command::new(program);
    command.creation_flags(NO_WINDOW);
    command
}
pub(super) fn route_preflight() -> Result<(), &'static str> {
    // Read-only verification after the explicit, VPN-only handoff.
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
    key.len() == 44 && STANDARD.decode(key).is_ok_and(|bytes| bytes.len() == 32)
}
fn generate_keypair() -> Result<(Zeroizing<String>, String), &'static str> {
    let mut bytes = Zeroizing::new([0u8; 32]);
    getrandom::fill(bytes.as_mut()).map_err(|_| FAILED)?;
    let secret = x25519_dalek::StaticSecret::from(*bytes);
    let public = x25519_dalek::PublicKey::from(&secret);
    Ok((
        Zeroizing::new(STANDARD.encode(secret.to_bytes())),
        STANDARD.encode(public.as_bytes()),
    ))
}
#[tauri::command]
pub async fn wg_prepare(app: AppHandle) -> Result<String, &'static str> {
    tauri::async_runtime::spawn_blocking(move || {
        route_preflight()?;
        if super::vpn_service::process_id()?.is_none() {
            return Err(super::vpn_service::ERROR);
        }
        let (key, public) = generate_keypair()?;
        *app.state::<WireGuardState>()
            .key
            .lock()
            .map_err(|_| FAILED)? = Some(key);
        Ok(public)
    })
    .await
    .map_err(|_| FAILED)?
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
pub async fn wg_start_routed(
    app: AppHandle,
    configuration: Configuration,
    session_id: String,
    country: String,
    routing: serde_json::Value,
) -> Result<(), &'static str> {
    // The private key never enters the renderer. The engine validates the
    // bounded profile and routing schema before opening a tunnel.
    validate(&configuration)?;
    let key = app
        .state::<WireGuardState>()
        .key
        .lock()
        .map_err(|_| FAILED)?
        .take()
        .ok_or(FAILED)?;
    let endpoint: SocketAddr = configuration.endpoint.parse().map_err(|_| FAILED)?;
    let mut profile = serde_json::json!({
        "version": 1, "session": session_id, "country": country, "method": "WIREGUARD",
        "server": endpoint.ip().to_string(), "port": endpoint.port(),
        "secret": key.as_str(), "public_key": configuration.server_public_key,
        "address": configuration.address, "routing": routing,
    });
    let result = super::managed::engine_start(app, profile.clone()).await;
    if let Some(serde_json::Value::String(secret)) = profile.get_mut("secret") {
        use zeroize::Zeroize;
        secret.zeroize();
    }
    result
}
#[tauri::command]
pub async fn wg_stop(app: AppHandle) -> Result<(), &'static str> {
    *app.state::<WireGuardState>()
        .key
        .lock()
        .map_err(|_| FAILED)? = None;
    super::managed::engine_stop(app).await
}
pub(super) async fn verify_tunnel(
    local: Ipv4Addr,
    identifier: uuid::Uuid,
    access_token: String,
    managed: bool,
) -> Result<bool, &'static str> {
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
    let path = if managed {
        "sessions"
    } else {
        "wireguard/sessions"
    };
    let mut response = client
        .get(format!("https://{HOST}/vpn/{path}/{identifier}/probe"))
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
    fn native_keys_are_fresh_and_form_a_valid_x25519_pair() {
        let (private, public) = generate_keypair().unwrap();
        assert!(valid_key(&private) && valid_key(&public));
        let raw: [u8; 32] = STANDARD
            .decode(private.as_str())
            .unwrap()
            .try_into()
            .unwrap();
        let derived = x25519_dalek::PublicKey::from(&x25519_dalek::StaticSecret::from(raw));
        assert_eq!(STANDARD.encode(derived.as_bytes()), public);
        assert_ne!(generate_keypair().unwrap().1, public);
    }
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
