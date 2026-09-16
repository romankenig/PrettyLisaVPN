use std::net::{IpAddr, Ipv4Addr, SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use ipnet::IpNet;
use serde::{Deserialize, Serialize};
#[cfg(windows)]
use windows_sys::Win32::{
    Foundation::{ERROR_OBJECT_ALREADY_EXISTS, ERROR_SUCCESS},
    NetworkManagement::{
        IpHelper::{
            CreateIpForwardEntry2, DeleteIpForwardEntry2, FreeMibTable, GetBestRoute2,
            GetIpForwardTable2, InitializeIpForwardEntry, MIB_IPFORWARD_ROW2, MIB_IPFORWARD_TABLE2,
        },
        Ndis::NET_LUID_LH,
    },
    Networking::WinSock::{AF_INET, IN_ADDR, SOCKADDR_INET},
};
use wireguard_nt::{Adapter, AdapterLoggingLevel, SetInterface, SetPeer};
use zeroize::Zeroize;

use crate::wireguard_keys::WireGuardKeyState;

const ADAPTER_NAME: &str = "PrettyLisaVPN";
const ADAPTER_POOL: &str = "PrettyLisaVPN";
const KEEPALIVE_SECONDS: u16 = 25;
const MAX_ALLOWED_IPS: usize = 64;
const MAX_DNS_SERVERS: usize = 4;
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(8);
const HANDSHAKE_POLL_INTERVAL: Duration = Duration::from_millis(100);
const DATA_PLANE_TIMEOUT: Duration = Duration::from_secs(8);
// 1280 remains safe when PrettyLisaVPN is carried inside another VPN while still
// satisfying the IPv6 minimum MTU. The MVP is IPv4-only, but using this floor also
// avoids HTTPS stalls caused by an outer tunnel silently dropping oversized packets.
const TUNNEL_MTU_ARGUMENT: &str = "mtu=1280";
// Some endpoint-security VPNs install the usual four /2 full-tunnel routes.
// Eight /3 routes remain provider-neutral, cover all IPv4, and ensure Windows
// selects PrettyLisaVPN without changing or removing another product's routes.
const FULL_TUNNEL_ROUTE_PREFIXES: [(Ipv4Addr, u8); 8] = [
    (Ipv4Addr::new(0, 0, 0, 0), 3),
    (Ipv4Addr::new(32, 0, 0, 0), 3),
    (Ipv4Addr::new(64, 0, 0, 0), 3),
    (Ipv4Addr::new(96, 0, 0, 0), 3),
    (Ipv4Addr::new(128, 0, 0, 0), 3),
    (Ipv4Addr::new(160, 0, 0, 0), 3),
    (Ipv4Addr::new(192, 0, 0, 0), 3),
    (Ipv4Addr::new(224, 0, 0, 0), 3),
];

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
    #[cfg(windows)]
    routes: Vec<MIB_IPFORWARD_ROW2>,
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
        #[cfg(windows)]
        let endpoint_route = pre_tunnel_ipv4_default_route()?;
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
        if adapter
            .set_default_route(&[parsed.client_address], &interface)
            .is_err()
        {
            let _ = adapter.down();
            return Err(TunnelError::Unavailable);
        }
        #[cfg(windows)]
        let routes =
            match configure_full_tunnel_routes(&adapter, parsed.endpoint.ip(), endpoint_route) {
                Ok(routes) => routes,
                Err(error) => {
                    let _ = adapter.down();
                    return Err(error);
                }
            };
        if adapter.up().is_err() {
            #[cfg(windows)]
            remove_routes(&routes);
            let _ = adapter.down();
            return Err(TunnelError::Unavailable);
        }
        if configure_interface().is_err() {
            #[cfg(windows)]
            remove_routes(&routes);
            let _ = adapter.down();
            return Err(TunnelError::PrivilegesRequired);
        }

        #[cfg(windows)]
        match full_tunnel_routes_are_selected(&adapter) {
            Ok(true) => {}
            Ok(false) | Err(_) => {
                remove_routes(&routes);
                let _ = adapter.down();
                return Err(TunnelError::Unavailable);
            }
        }
        if wait_for_handshake(&adapter).is_err() {
            #[cfg(windows)]
            remove_routes(&routes);
            let _ = adapter.down();
            return Err(TunnelError::HandshakeTimeout);
        }
        if verify_data_plane().is_err() {
            #[cfg(windows)]
            remove_routes(&routes);
            let _ = adapter.down();
            return Err(TunnelError::DataPlaneUnavailable);
        }
        if let Err(error) = configure_dns(&parsed.dns) {
            #[cfg(windows)]
            remove_routes(&routes);
            let _ = adapter.down();
            return Err(error);
        }

        *active = Some(ActiveTunnel {
            adapter,
            #[cfg(windows)]
            routes,
        });
        Ok(TunnelStatus::Up)
    }

    fn stop(&self) -> Result<TunnelStatus, TunnelError> {
        let mut active = self.active.lock().map_err(|_| TunnelError::Unavailable)?;
        if let Some(tunnel) = active.as_ref() {
            // Bringing the dedicated adapter down removes its default routes and makes
            // its adapter-scoped DNS inactive, restoring the original Windows network path.
            // Keep the handle on failure so a later idempotent stop can retry safely.
            #[cfg(windows)]
            remove_routes(&tunnel.routes);
            tunnel
                .adapter
                .down()
                .map_err(|_| TunnelError::Unavailable)?;
        }
        *active = None;
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

#[cfg(windows)]
fn ipv4_sockaddr(address: Ipv4Addr) -> SOCKADDR_INET {
    let mut socket = SOCKADDR_INET::default();
    socket.Ipv4.sin_family = AF_INET;
    socket.Ipv4.sin_addr = IN_ADDR {
        S_un: windows_sys::Win32::Networking::WinSock::IN_ADDR_0 {
            S_addr: u32::from_ne_bytes(address.octets()),
        },
    };
    socket
}

#[cfg(windows)]
fn best_ipv4_route(endpoint: IpAddr) -> Result<MIB_IPFORWARD_ROW2, TunnelError> {
    let IpAddr::V4(endpoint) = endpoint else {
        return Err(TunnelError::InvalidConfiguration);
    };
    let destination = ipv4_sockaddr(endpoint);
    let mut route = MIB_IPFORWARD_ROW2::default();
    let mut source = SOCKADDR_INET::default();
    let result = unsafe {
        GetBestRoute2(
            std::ptr::null(),
            0,
            std::ptr::null(),
            &destination,
            0,
            &mut route,
            &mut source,
        )
    };
    if result == ERROR_SUCCESS {
        Ok(route)
    } else {
        Err(TunnelError::Unavailable)
    }
}

#[cfg(windows)]
fn pre_tunnel_ipv4_default_route() -> Result<MIB_IPFORWARD_ROW2, TunnelError> {
    let mut table: *mut MIB_IPFORWARD_TABLE2 = std::ptr::null_mut();
    let result = unsafe { GetIpForwardTable2(AF_INET, &mut table) };
    if result != ERROR_SUCCESS || table.is_null() {
        return Err(TunnelError::Unavailable);
    }

    let selected = unsafe {
        let table_ref = &*table;
        std::slice::from_raw_parts(table_ref.Table.as_ptr(), table_ref.NumEntries as usize)
            .iter()
            .filter(|route| {
                route.DestinationPrefix.PrefixLength == 0
                    && route.DestinationPrefix.Prefix.si_family == AF_INET
                    && route.NextHop.si_family == AF_INET
                    && route.NextHop.Ipv4.sin_addr.S_un.S_addr != 0
                    && !route.Loopback
            })
            .min_by_key(|route| route.Metric)
            .copied()
    };
    unsafe { FreeMibTable(table.cast()) };
    selected.ok_or(TunnelError::Unavailable)
}

#[cfg(windows)]
fn route_for_interface(luid: u64, destination: Ipv4Addr, prefix: u8) -> MIB_IPFORWARD_ROW2 {
    let mut route = MIB_IPFORWARD_ROW2::default();
    unsafe { InitializeIpForwardEntry(&mut route) };
    route.InterfaceLuid = unsafe { std::mem::transmute::<u64, NET_LUID_LH>(luid) };
    route.DestinationPrefix.Prefix = ipv4_sockaddr(destination);
    route.DestinationPrefix.PrefixLength = prefix;
    route.NextHop.si_family = AF_INET;
    route.Metric = 0;
    route
}

#[cfg(windows)]
fn configure_full_tunnel_routes(
    adapter: &Adapter,
    endpoint: IpAddr,
    existing_endpoint_route: MIB_IPFORWARD_ROW2,
) -> Result<Vec<MIB_IPFORWARD_ROW2>, TunnelError> {
    let IpAddr::V4(endpoint) = endpoint else {
        return Err(TunnelError::InvalidConfiguration);
    };
    let mut installed = Vec::with_capacity(FULL_TUNNEL_ROUTE_PREFIXES.len() + 1);

    let mut endpoint_bypass = MIB_IPFORWARD_ROW2::default();
    unsafe { InitializeIpForwardEntry(&mut endpoint_bypass) };
    endpoint_bypass.InterfaceLuid = existing_endpoint_route.InterfaceLuid;
    endpoint_bypass.InterfaceIndex = existing_endpoint_route.InterfaceIndex;
    endpoint_bypass.DestinationPrefix.Prefix = ipv4_sockaddr(endpoint);
    endpoint_bypass.DestinationPrefix.PrefixLength = 32;
    endpoint_bypass.NextHop = existing_endpoint_route.NextHop;
    endpoint_bypass.Metric = 0;
    install_route(endpoint_bypass, &mut installed)?;

    for (network, prefix) in FULL_TUNNEL_ROUTE_PREFIXES {
        let route = route_for_interface(adapter.get_luid(), network, prefix);
        if let Err(error) = install_route(route, &mut installed) {
            remove_routes(&installed);
            return Err(error);
        }
    }
    Ok(installed)
}

#[cfg(windows)]
fn install_route(
    route: MIB_IPFORWARD_ROW2,
    installed: &mut Vec<MIB_IPFORWARD_ROW2>,
) -> Result<(), TunnelError> {
    let result = unsafe { CreateIpForwardEntry2(&route) };
    if result == ERROR_SUCCESS {
        installed.push(route);
        Ok(())
    } else if result == ERROR_OBJECT_ALREADY_EXISTS {
        Ok(())
    } else {
        Err(TunnelError::Unavailable)
    }
}

#[cfg(windows)]
fn remove_routes(routes: &[MIB_IPFORWARD_ROW2]) {
    for route in routes.iter().rev() {
        let _ = unsafe { DeleteIpForwardEntry2(route) };
    }
}

#[cfg(windows)]
fn full_tunnel_routes_are_selected(adapter: &Adapter) -> Result<bool, TunnelError> {
    for address in [Ipv4Addr::new(1, 1, 1, 1), Ipv4Addr::new(129, 1, 1, 1)] {
        let route = best_ipv4_route(IpAddr::V4(address))?;
        let route_luid = unsafe { std::mem::transmute::<NET_LUID_LH, u64>(route.InterfaceLuid) };
        if route_luid != adapter.get_luid() {
            return Ok(false);
        }
    }
    Ok(true)
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
        if !matches!(client_address, IpNet::V4(_)) || client_address.addr().is_unspecified() {
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
        if dns.iter().any(|server| match server {
            IpAddr::V4(address) => {
                address.is_unspecified()
                    || address.is_broadcast()
                    || address.is_loopback()
                    || address.is_multicast()
            }
            IpAddr::V6(_) => true,
        }) {
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
        let ipv4_default = "0.0.0.0/0"
            .parse::<IpNet>()
            .map_err(|_| TunnelError::InvalidConfiguration)?;
        if allowed_ips.as_slice() != [ipv4_default] {
            return Err(TunnelError::InvalidConfiguration);
        }

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
    HandshakeTimeout,
    DataPlaneUnavailable,
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
            Self::HandshakeTimeout => "wireguard_handshake_timeout",
            Self::DataPlaneUnavailable => "wireguard_data_plane_unavailable",
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

fn configure_interface() -> Result<(), TunnelError> {
    let netsh = std::env::var_os("SystemRoot")
        .map(PathBuf::from)
        .map(|root| root.join("System32").join("netsh.exe"))
        .filter(|path| path.is_file())
        .ok_or(TunnelError::Unavailable)?;

    let mut command = Command::new(&netsh);
    command
        .args([
            "interface",
            "ipv4",
            "set",
            "subinterface",
            ADAPTER_NAME,
            TUNNEL_MTU_ARGUMENT,
            "store=active",
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x0800_0000);
    }
    if !command
        .status()
        .map_err(|_| TunnelError::Unavailable)?
        .success()
    {
        return Err(TunnelError::PrivilegesRequired);
    }
    Ok(())
}

fn wait_for_handshake(adapter: &Adapter) -> Result<(), TunnelError> {
    let socket = std::net::UdpSocket::bind((Ipv4Addr::UNSPECIFIED, 0))
        .map_err(|_| TunnelError::Unavailable)?;
    socket
        .send_to(&[0], (Ipv4Addr::new(1, 1, 1, 1), 9))
        .map_err(|_| TunnelError::Unavailable)?;

    let deadline = Instant::now() + HANDSHAKE_TIMEOUT;
    while Instant::now() < deadline {
        if adapter
            .get_config()
            .peers
            .iter()
            .any(|peer| peer.last_handshake.is_some())
        {
            return Ok(());
        }
        thread::sleep(HANDSHAKE_POLL_INTERVAL);
    }
    Err(TunnelError::HandshakeTimeout)
}

fn verify_data_plane() -> Result<(), TunnelError> {
    TcpStream::connect_timeout(
        &SocketAddr::new(IpAddr::V4(Ipv4Addr::new(1, 1, 1, 1)), 443),
        DATA_PLANE_TIMEOUT,
    )
    .map(|_| ())
    .map_err(|_| TunnelError::DataPlaneUnavailable)
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
    fn coexistence_routes_cover_ipv4_more_specifically_than_competing_vpn_routes() {
        let routes = FULL_TUNNEL_ROUTE_PREFIXES
            .iter()
            .map(|(address, prefix)| ipnet::Ipv4Net::new(*address, *prefix).unwrap())
            .collect::<Vec<_>>();

        for address in [
            Ipv4Addr::new(1, 1, 1, 1),
            Ipv4Addr::new(33, 1, 1, 1),
            Ipv4Addr::new(64, 0, 0, 1),
            Ipv4Addr::new(97, 0, 0, 1),
            Ipv4Addr::new(128, 0, 0, 1),
            Ipv4Addr::new(161, 0, 0, 1),
            Ipv4Addr::new(192, 0, 0, 1),
            Ipv4Addr::new(255, 255, 255, 254),
        ] {
            assert_eq!(
                routes
                    .iter()
                    .filter(|route| route.contains(&address))
                    .count(),
                1
            );
        }
        assert!(routes.iter().all(|route| route.prefix_len() == 3));
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

        let mut split_tunnel = valid_configuration();
        split_tunnel.allowed_ips = vec!["10.0.0.0/8".into()];
        assert!(ParsedConfiguration::try_from(split_tunnel).is_err());

        let mut mixed_routes = valid_configuration();
        mixed_routes.allowed_ips.push("10.0.0.0/8".into());
        assert!(ParsedConfiguration::try_from(mixed_routes).is_err());

        let mut ipv6_dns = valid_configuration();
        ipv6_dns.dns = vec!["2606:4700:4700::1111".into()];
        assert!(ParsedConfiguration::try_from(ipv6_dns).is_err());

        let mut ipv6_client = valid_configuration();
        ipv6_client.client_address = "fd00::2/128".into();
        assert!(ParsedConfiguration::try_from(ipv6_client).is_err());
    }

    #[test]
    fn error_codes_do_not_contain_configuration_or_keys() {
        assert_eq!(
            TunnelError::InvalidConfiguration.code(),
            "invalid_wireguard_configuration"
        );
        assert_eq!(TunnelError::KeyMissing.code(), "wireguard_key_missing");
        assert_eq!(
            TunnelError::HandshakeTimeout.code(),
            "wireguard_handshake_timeout"
        );
        assert_eq!(
            TunnelError::DataPlaneUnavailable.code(),
            "wireguard_data_plane_unavailable"
        );
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
