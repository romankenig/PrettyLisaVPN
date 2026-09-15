use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::Mutex;

use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use ipnet::IpNet;
use serde::{Deserialize, Serialize};
use wireguard_nt::{Adapter, AdapterLoggingLevel, SetInterface, SetPeer};
use zeroize::Zeroize;

use crate::wireguard_keys::WireGuardKeyState;

const ADAPTER_NAME: &str = "PrettyLisaVPN";
const ADAPTER_POOL: &str = "PrettyLisaVPN";
const KEEPALIVE_SECONDS: u16 = 25;
const MAX_ALLOWED_IPS: usize = 64;
const MAX_DNS_SERVERS: usize = 4;

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct TunnelConfiguration {
    endpoint: TunnelEndpoint,
    server_public_key: String,
    client_address: String,
    dns: Vec<String>,
    allowed_ips: Vec<String>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct TunnelEndpoint {
    ipv4: String,
    port: u16,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum TunnelStatus {
    Down,
    Up,
}

struct ActiveTunnel {
    adapter: Adapter,
}

pub struct WireGuardTunnelState {
    active: Mutex<Option<ActiveTunnel>>,
}

impl WireGuardTunnelState {
    pub fn new() -> Self {
        Self {
            active: Mutex::new(None),
        }
    }

    fn start(
        &self,
        configuration: TunnelConfiguration,
        keys: &WireGuardKeyState,
    ) -> Result<TunnelStatus, TunnelError> {
        let parsed = ParsedConfiguration::try_from(configuration)?;
        let mut active = self.active.lock().map_err(|_| TunnelError::Unavailable)?;
        if let Some(current) = active.as_ref() {
            return current
                .adapter
                .is_up()
                .map(|up| {
                    if up {
                        TunnelStatus::Up
                    } else {
                        TunnelStatus::Down
                    }
                })
                .map_err(|_| TunnelError::Unavailable);
        }

        let private_key = keys
            .read_private_key()
            .map_err(|_| TunnelError::KeyUnavailable)?
            .ok_or(TunnelError::KeyMissing)?;
        let library_path = wireguard_library_path()?;
        // SAFETY: the absolute path is fixed beside our signed executable. Release packaging
        // must supply the official signed WireGuardNT DLL and verify its pinned digest.
        let wireguard = unsafe { wireguard_nt::load_from_path(library_path) }
            .map_err(|_| TunnelError::ComponentMissing)?;
        let adapter = Adapter::open(&wireguard, ADAPTER_NAME)
            .or_else(|_| Adapter::create(&wireguard, ADAPTER_POOL, ADAPTER_NAME, None))
            .map_err(|_| TunnelError::PrivilegesRequired)?;
        adapter.set_logging(AdapterLoggingLevel::Off);

        let mut interface = SetInterface {
            listen_port: None,
            public_key: None,
            private_key: Some(*private_key),
            peers: vec![SetPeer {
                public_key: Some(parsed.server_public_key),
                preshared_key: None,
                keep_alive: Some(KEEPALIVE_SECONDS),
                endpoint: parsed.endpoint,
                allowed_ips: parsed.allowed_ips,
            }],
        };

        let configured = adapter.set_config(&interface);
        if let Some(key) = interface.private_key.as_mut() {
            key.zeroize();
        }
        configured.map_err(|_| TunnelError::Unavailable)?;
        adapter
            .set_default_route(&[parsed.client_address], &interface)
            .map_err(|_| TunnelError::Unavailable)?;
        configure_dns(&parsed.dns)?;
        adapter.up().map_err(|_| TunnelError::Unavailable)?;

        *active = Some(ActiveTunnel { adapter });
        Ok(TunnelStatus::Up)
    }

    fn stop(&self) -> Result<TunnelStatus, TunnelError> {
        let mut active = self.active.lock().map_err(|_| TunnelError::Unavailable)?;
        if let Some(tunnel) = active.take() {
            tunnel
                .adapter
                .down()
                .map_err(|_| TunnelError::Unavailable)?;
        }
        Ok(TunnelStatus::Down)
    }

    fn status(&self) -> Result<TunnelStatus, TunnelError> {
        let active = self.active.lock().map_err(|_| TunnelError::Unavailable)?;
        match active.as_ref() {
            None => Ok(TunnelStatus::Down),
            Some(tunnel) => tunnel
                .adapter
                .is_up()
                .map(|up| {
                    if up {
                        TunnelStatus::Up
                    } else {
                        TunnelStatus::Down
                    }
                })
                .map_err(|_| TunnelError::Unavailable),
        }
    }
}

struct ParsedConfiguration {
    endpoint: SocketAddr,
    server_public_key: [u8; 32],
    client_address: IpNet,
    dns: Vec<IpAddr>,
    allowed_ips: Vec<IpNet>,
}

impl TryFrom<TunnelConfiguration> for ParsedConfiguration {
    type Error = TunnelError;

    fn try_from(value: TunnelConfiguration) -> Result<Self, Self::Error> {
        let endpoint_ip = value
            .endpoint
            .ipv4
            .parse::<Ipv4Addr>()
            .map_err(|_| TunnelError::InvalidConfiguration)?;
        if endpoint_ip.is_unspecified() || endpoint_ip.is_multicast() || value.endpoint.port == 0 {
            return Err(TunnelError::InvalidConfiguration);
        }
        let server_public_key = decode_public_key(&value.server_public_key)?;
        let client_address = value
            .client_address
            .parse::<IpNet>()
            .map_err(|_| TunnelError::InvalidConfiguration)?;
        if client_address.addr().is_unspecified() {
            return Err(TunnelError::InvalidConfiguration);
        }
        if value.dns.is_empty() || value.dns.len() > MAX_DNS_SERVERS {
            return Err(TunnelError::InvalidConfiguration);
        }
        let dns = value
            .dns
            .iter()
            .map(|server| server.parse::<IpAddr>())
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| TunnelError::InvalidConfiguration)?;
        if dns.iter().any(IpAddr::is_unspecified) {
            return Err(TunnelError::InvalidConfiguration);
        }
        if value.allowed_ips.is_empty() || value.allowed_ips.len() > MAX_ALLOWED_IPS {
            return Err(TunnelError::InvalidConfiguration);
        }
        let allowed_ips = value
            .allowed_ips
            .iter()
            .map(|network| network.parse::<IpNet>())
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| TunnelError::InvalidConfiguration)?;

        Ok(Self {
            endpoint: SocketAddr::new(IpAddr::V4(endpoint_ip), value.endpoint.port),
            server_public_key,
            client_address,
            dns,
            allowed_ips,
        })
    }
}

#[derive(Debug)]
enum TunnelError {
    InvalidConfiguration,
    KeyMissing,
    KeyUnavailable,
    ComponentMissing,
    PrivilegesRequired,
    Unavailable,
}

impl TunnelError {
    fn code(&self) -> &'static str {
        match self {
            Self::InvalidConfiguration => "invalid_wireguard_configuration",
            Self::KeyMissing => "wireguard_key_missing",
            Self::KeyUnavailable => "wireguard_key_storage_unavailable",
            Self::ComponentMissing => "wireguard_component_missing",
            Self::PrivilegesRequired => "administrator_privileges_required",
            Self::Unavailable => "wireguard_tunnel_unavailable",
        }
    }
}

#[tauri::command]
pub fn start_wireguard_tunnel(
    configuration: TunnelConfiguration,
    tunnel: tauri::State<'_, WireGuardTunnelState>,
    keys: tauri::State<'_, WireGuardKeyState>,
) -> Result<TunnelStatus, &'static str> {
    tunnel
        .start(configuration, &keys)
        .map_err(|error| error.code())
}

#[tauri::command]
pub fn stop_wireguard_tunnel(
    tunnel: tauri::State<'_, WireGuardTunnelState>,
) -> Result<TunnelStatus, &'static str> {
    tunnel.stop().map_err(|error| error.code())
}

#[tauri::command]
pub fn get_wireguard_tunnel_state(
    tunnel: tauri::State<'_, WireGuardTunnelState>,
) -> Result<TunnelStatus, &'static str> {
    tunnel.status().map_err(|error| error.code())
}

fn decode_public_key(encoded: &str) -> Result<[u8; 32], TunnelError> {
    let decoded = STANDARD
        .decode(encoded)
        .map_err(|_| TunnelError::InvalidConfiguration)?;
    let key: [u8; 32] = decoded
        .try_into()
        .map_err(|_| TunnelError::InvalidConfiguration)?;
    if key.iter().all(|byte| *byte == 0) {
        return Err(TunnelError::InvalidConfiguration);
    }
    Ok(key)
}

fn wireguard_library_path() -> Result<PathBuf, TunnelError> {
    let executable = std::env::current_exe().map_err(|_| TunnelError::ComponentMissing)?;
    let directory = executable.parent().ok_or(TunnelError::ComponentMissing)?;
    let library = directory.join("wireguard.dll");
    if !library.is_file() {
        return Err(TunnelError::ComponentMissing);
    }
    Ok(library)
}

fn configure_dns(servers: &[IpAddr]) -> Result<(), TunnelError> {
    let netsh = std::env::var_os("SystemRoot")
        .map(PathBuf::from)
        .map(|root| root.join("System32").join("netsh.exe"))
        .filter(|path| path.is_file())
        .ok_or(TunnelError::Unavailable)?;

    let mut ipv4_index = 0;
    let mut ipv6_index = 0;
    for server in servers {
        let family = if server.is_ipv4() { "ipv4" } else { "ipv6" };
        let family_index = if server.is_ipv4() {
            ipv4_index += 1;
            ipv4_index
        } else {
            ipv6_index += 1;
            ipv6_index
        };
        let action = if family_index == 1 { "set" } else { "add" };
        let mut command = Command::new(&netsh);
        command
            .args(["interface", family, action, "dnsservers"])
            .arg(format!("name={ADAPTER_NAME}"));
        if family_index == 1 {
            command.arg("source=static");
        }
        command
            .arg(format!("address={server}"))
            .arg(format!("index={family_index}"))
            .arg("validate=no")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x0800_0000);
        }
        let status = command.status().map_err(|_| TunnelError::Unavailable)?;
        if !status.success() {
            return Err(TunnelError::PrivilegesRequired);
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_configuration() -> TunnelConfiguration {
        TunnelConfiguration {
            endpoint: TunnelEndpoint {
                ipv4: "204.48.17.50".into(),
                port: 51820,
            },
            server_public_key: "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE=".into(),
            client_address: "10.77.0.2/16".into(),
            dns: vec!["1.1.1.1".into(), "1.0.0.1".into()],
            allowed_ips: vec!["0.0.0.0/0".into()],
        }
    }

    #[test]
    fn accepts_complete_backend_transport_configuration() {
        let parsed = ParsedConfiguration::try_from(valid_configuration()).unwrap();
        assert_eq!(parsed.endpoint, "204.48.17.50:51820".parse().unwrap());
        assert_eq!(parsed.client_address.to_string(), "10.77.0.2/16");
        assert_eq!(parsed.allowed_ips[0].to_string(), "0.0.0.0/0");
        assert_eq!(parsed.dns.len(), 2);
    }

    #[test]
    fn rejects_invalid_or_incomplete_configuration() {
        let mut invalid_key = valid_configuration();
        invalid_key.server_public_key = "not-a-key".into();
        assert!(ParsedConfiguration::try_from(invalid_key).is_err());

        let mut missing_routes = valid_configuration();
        missing_routes.allowed_ips.clear();
        assert!(ParsedConfiguration::try_from(missing_routes).is_err());

        let mut missing_dns = valid_configuration();
        missing_dns.dns.clear();
        assert!(ParsedConfiguration::try_from(missing_dns).is_err());

        let mut invalid_endpoint = valid_configuration();
        invalid_endpoint.endpoint.ipv4 = "0.0.0.0".into();
        assert!(ParsedConfiguration::try_from(invalid_endpoint).is_err());
    }

    #[test]
    fn error_codes_do_not_contain_configuration_or_keys() {
        assert_eq!(
            TunnelError::InvalidConfiguration.code(),
            "invalid_wireguard_configuration"
        );
        assert_eq!(TunnelError::KeyMissing.code(), "wireguard_key_missing");
        assert_eq!(
            TunnelError::ComponentMissing.code(),
            "wireguard_component_missing"
        );
    }

    #[test]
    fn fresh_tunnel_is_down_and_stop_is_idempotent() {
        let tunnel = WireGuardTunnelState::new();

        assert_eq!(tunnel.status().unwrap(), TunnelStatus::Down);
        assert_eq!(tunnel.stop().unwrap(), TunnelStatus::Down);
        assert_eq!(tunnel.stop().unwrap(), TunnelStatus::Down);
    }
}
