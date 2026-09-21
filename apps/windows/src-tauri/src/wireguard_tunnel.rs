use std::net::{IpAddr, Ipv4Addr, SocketAddr};
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

use crate::debug_log;
use crate::obfuscation_transport::{ActivePacketTransport, TransportError, TransportMode};
use crate::packet_obfuscation::{self, ObfuscationConfig};
use crate::wireguard_keys::WireGuardKeyState;

const ADAPTER_NAME: &str = "PrettyLisaVPN";
const ADAPTER_POOL: &str = "PrettyLisaVPN";
const KEEPALIVE_SECONDS: u16 = 25;
const MAX_ALLOWED_IPS: usize = 64;
const MAX_DNS_SERVERS: usize = 4;
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(8);
const HANDSHAKE_POLL_INTERVAL: Duration = Duration::from_millis(100);
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
    #[serde(default)]
    obfuscation: Option<ObfuscationConfig>,
    #[serde(default)]
    direct: bool,
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

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct WireGuardPeerDiagnostics {
    peer_public_key: String,
    endpoint: String,
    allowed_ips: Vec<String>,
    persistent_keepalive: u16,
    tx_bytes: u64,
    rx_bytes: u64,
    transport_mode: TransportMode,
    transport_healthy: bool,
    public_endpoint: String,
}

struct ActiveTunnel {
    client_ip: IpAddr,
    dns: Vec<IpAddr>,
    obfuscation: Option<ObfuscationConfig>,
    adapter: Adapter,
    transport: ActivePacketTransport,
    #[cfg(windows)]
    routes: Vec<MIB_IPFORWARD_ROW2>,
    cleaned: bool,
}

impl ActiveTunnel {
    fn cleanup(&mut self) -> Result<(), TunnelError> {
        if self.cleaned {
            debug_log::event(
                "tunnel_cleanup_skipped",
                format_args!("reason=already_cleaned"),
            );
            return Ok(());
        }
        debug_log::event(
            "tunnel_cleanup_started",
            format_args!(
                "transport_mode={:?} transport_counters={:?}",
                self.transport.mode(),
                self.transport.snapshot()
            ),
        );
        let adapter_result = self.adapter.down();
        #[cfg(windows)]
        remove_routes(&self.routes);
        self.transport.stop();
        self.cleaned = adapter_result.is_ok();
        debug_log::event(
            "tunnel_cleanup_finished",
            format_args!(
                "adapter_down={} cleaned={}",
                adapter_result.is_ok(),
                self.cleaned
            ),
        );
        adapter_result.map_err(|_| TunnelError::Unavailable)
    }
}

impl Drop for ActiveTunnel {
    fn drop(&mut self) {
        let _ = self.cleanup();
    }
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
        debug_log::event(
            "tunnel_start_parsed",
            format_args!(
                "backend_endpoint={} client_address={} dns_servers={} allowed_ips={:?}",
                parsed.public_endpoint,
                parsed.client_address,
                parsed.dns.len(),
                parsed.allowed_ips
            ),
        );
        let mut active = self.active.lock().map_err(|_| TunnelError::Unavailable)?;
        if let Some(current) = active.as_ref() {
            if current.transport.is_healthy() && current.adapter.is_up().unwrap_or(false) {
                if parsed.obfuscation != current.obfuscation
                    || (parsed.obfuscation.is_some()
                        && current.transport.public_endpoint() != parsed.public_endpoint)
                {
                    return Err(TunnelError::InvalidConfiguration);
                }
                if parsed.direct
                    && (current.transport.mode() != TransportMode::Direct
                        || current.transport.public_endpoint() != parsed.public_endpoint)
                {
                    return Err(TunnelError::InvalidConfiguration);
                }
                debug_log::event("tunnel_start_reused", format_args!("status=UP"));
                return Ok(TunnelStatus::Up);
            }
            debug_log::event(
                "tunnel_stale_instance_detected",
                format_args!("action=cleanup"),
            );
            if let Some(mut stale) = active.take() {
                let _ = stale.cleanup();
            }
        }

        let private_key = keys
            .read_private_key()
            .map_err(|_| TunnelError::KeyUnavailable)?
            .ok_or(TunnelError::KeyMissing)?;
        debug_log::event(
            "wireguard_private_key_loaded",
            format_args!("source=credential_manager"),
        );
        let packet_transport = if let Some(config) = &parsed.obfuscation {
            ActivePacketTransport::start_configured(parsed.public_endpoint, config)?
        } else if parsed.direct {
            ActivePacketTransport::Direct {
                public_endpoint: parsed.public_endpoint,
            }
        } else {
            ActivePacketTransport::start(parsed.public_endpoint)?
        };
        if !packet_transport.is_healthy() {
            return Err(TunnelError::TransportUnavailable);
        }
        let wireguard_endpoint = packet_transport.wireguard_endpoint();
        #[cfg(windows)]
        let endpoint_route = pre_tunnel_ipv4_default_route()?;
        #[cfg(windows)]
        debug_log::event(
            "physical_route_captured",
            format_args!(
                "interface_index={} route_metric={}",
                endpoint_route.InterfaceIndex, endpoint_route.Metric
            ),
        );
        let library_path = wireguard_library_path()?;
        debug_log::event(
            "wireguard_component_found",
            format_args!("component={}", library_path.display()),
        );
        // SAFETY: the absolute path is fixed beside our signed executable. Release packaging
        // must supply the official signed WireGuardNT DLL and verify its pinned digest.
        let wireguard = unsafe { wireguard_nt::load_from_path(library_path) }
            .map_err(|_| TunnelError::ComponentMissing)?;
        let adapter = Adapter::open(&wireguard, ADAPTER_NAME)
            .or_else(|_| Adapter::create(&wireguard, ADAPTER_POOL, ADAPTER_NAME, None))
            .map_err(|_| TunnelError::PrivilegesRequired)?;
        adapter.set_logging(AdapterLoggingLevel::Off);
        debug_log::event(
            "wireguard_adapter_ready",
            format_args!("adapter={ADAPTER_NAME} luid={}", adapter.get_luid()),
        );

        let mut interface = SetInterface {
            listen_port: None,
            public_key: None,
            private_key: Some(*private_key),
            peers: vec![SetPeer {
                public_key: Some(parsed.server_public_key),
                preshared_key: None,
                keep_alive: Some(KEEPALIVE_SECONDS),
                endpoint: wireguard_endpoint,
                allowed_ips: parsed.allowed_ips.clone(),
            }],
        };

        debug_log::event(
            "wireguard_set_config_started",
            format_args!(
                "peer_endpoint={wireguard_endpoint} allowed_ips={:?}",
                parsed.allowed_ips
            ),
        );
        let configured = adapter.set_config(&interface);
        if let Some(key) = interface.private_key.as_mut() {
            key.zeroize();
        }
        configured.map_err(|_| TunnelError::Unavailable)?;
        debug_log::event(
            "wireguard_set_config_succeeded",
            format_args!("peer_count=1"),
        );
        let diagnostics = read_peer_diagnostics(&adapter, &packet_transport)?;
        log_peer_diagnostics("after_set_config", &diagnostics);
        if validate_peer_readback(&diagnostics, &parsed, wireguard_endpoint).is_err() {
            let _ = adapter.down();
            return Err(TunnelError::ConfigurationReadbackMismatch);
        }
        debug_log::event("wireguard_readback_validated", format_args!("result=match"));
        if adapter
            .set_default_route(&[parsed.client_address], &interface)
            .is_err()
        {
            let _ = adapter.down();
            return Err(TunnelError::Unavailable);
        }
        debug_log::event(
            "wireguard_address_configured",
            format_args!("client_address={}", parsed.client_address),
        );
        #[cfg(windows)]
        let routes = match configure_full_tunnel_routes(
            &adapter,
            parsed.public_endpoint.ip(),
            endpoint_route,
        ) {
            Ok(routes) => routes,
            Err(error) => {
                let _ = adapter.down();
                return Err(error);
            }
        };
        #[cfg(windows)]
        debug_log::event(
            "full_tunnel_routes_installed",
            format_args!("tracked_routes={}", routes.len()),
        );
        if adapter.up().is_err() {
            #[cfg(windows)]
            remove_routes(&routes);
            let _ = adapter.down();
            return Err(TunnelError::Unavailable);
        }
        debug_log::event("wireguard_adapter_up", format_args!("status=UP"));
        if configure_interface().is_err() {
            #[cfg(windows)]
            remove_routes(&routes);
            let _ = adapter.down();
            return Err(TunnelError::PrivilegesRequired);
        }
        debug_log::event("wireguard_mtu_configured", format_args!("mtu=1280"));

        #[cfg(windows)]
        match full_tunnel_routes_are_selected(&adapter) {
            Ok(true) => {}
            Ok(false) | Err(_) => {
                remove_routes(&routes);
                let _ = adapter.down();
                return Err(TunnelError::RouteLeakDetected);
            }
        }
        debug_log::event(
            "full_tunnel_route_selection_verified",
            format_args!("result=selected"),
        );
        if let Err(error) = wait_for_handshake(&adapter, &packet_transport) {
            #[cfg(windows)]
            remove_routes(&routes);
            let _ = adapter.down();
            return Err(error);
        }
        debug_log::event(
            "wireguard_handshake_verified",
            format_args!("result=success"),
        );
        if let Err(error) = configure_dns(&parsed.dns) {
            #[cfg(windows)]
            remove_routes(&routes);
            let _ = adapter.down();
            return Err(error);
        }
        debug_log::event(
            "wireguard_dns_configured",
            format_args!("server_count={}", parsed.dns.len()),
        );

        *active = Some(ActiveTunnel {
            client_ip: parsed.client_address.addr(),
            dns: parsed.dns.clone(),
            obfuscation: parsed.obfuscation.clone(),
            adapter,
            transport: packet_transport,
            #[cfg(windows)]
            routes,
            cleaned: false,
        });
        debug_log::event("tunnel_start_completed", format_args!("status=UP"));
        Ok(TunnelStatus::Up)
    }

    fn stop(&self) -> Result<TunnelStatus, TunnelError> {
        debug_log::event(
            "tunnel_stop_requested",
            format_args!("source=native_command"),
        );
        let mut active = self.active.lock().map_err(|_| TunnelError::Unavailable)?;
        if let Some(tunnel) = active.as_mut() {
            // Stop WireGuard first, remove its routes, then stop the local packet transport.
            // Retain the handle after a native error so an idempotent retry can finish cleanup.
            tunnel.cleanup()?;
        }
        *active = None;
        debug_log::event("tunnel_stop_completed", format_args!("status=DOWN"));
        Ok(TunnelStatus::Down)
    }

    fn status(&self) -> Result<TunnelStatus, TunnelError> {
        let mut active = self.active.lock().map_err(|_| TunnelError::Unavailable)?;
        let status = match active.as_ref() {
            None => Ok(TunnelStatus::Down),
            Some(tunnel) if !tunnel.transport.is_healthy() => Ok(TunnelStatus::Down),
            Some(tunnel) => tunnel
                .adapter
                .is_up()
                .map_or(Err(TunnelError::Unavailable), |up| {
                    Ok(if up {
                        TunnelStatus::Up
                    } else {
                        TunnelStatus::Down
                    })
                }),
        }?;
        if let Some(tunnel) = active.as_ref() {
            if debug_log::enabled() {
                if let Ok(diagnostics) = read_peer_diagnostics(&tunnel.adapter, &tunnel.transport) {
                    log_peer_diagnostics("state_poll", &diagnostics);
                    log_transport_diagnostics("state_poll", &tunnel.transport);
                }
            }
        }
        if status == TunnelStatus::Down {
            if let Some(mut tunnel) = active.take() {
                let _ = tunnel.cleanup();
            }
        }
        Ok(status)
    }

    fn diagnostics(&self) -> Result<Option<WireGuardPeerDiagnostics>, TunnelError> {
        let active = self.active.lock().map_err(|_| TunnelError::Unavailable)?;
        let Some(tunnel) = active.as_ref() else {
            return Ok(None);
        };
        let diagnostics = read_peer_diagnostics(&tunnel.adapter, &tunnel.transport)?;
        log_peer_diagnostics("runtime_snapshot", &diagnostics);
        log_transport_diagnostics("runtime_snapshot", &tunnel.transport);
        Ok(Some(diagnostics))
    }
}

impl Drop for WireGuardTunnelState {
    fn drop(&mut self) {
        if let Ok(active) = self.active.get_mut() {
            if let Some(mut tunnel) = active.take() {
                let _ = tunnel.cleanup();
            }
        }
    }
}

fn read_peer_diagnostics(
    adapter: &Adapter,
    transport: &ActivePacketTransport,
) -> Result<WireGuardPeerDiagnostics, TunnelError> {
    let configuration =
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| adapter.get_config()))
            .map_err(|_| TunnelError::Unavailable)?;
    if configuration.peers.len() != 1 {
        return Err(TunnelError::ConfigurationReadbackMismatch);
    }
    let peer = &configuration.peers[0];
    Ok(WireGuardPeerDiagnostics {
        peer_public_key: STANDARD.encode(peer.public_key),
        endpoint: peer.endpoint.to_string(),
        allowed_ips: peer.allowed_ips.iter().map(ToString::to_string).collect(),
        persistent_keepalive: peer.persistent_keepalive,
        tx_bytes: peer.tx_bytes,
        rx_bytes: peer.rx_bytes,
        transport_mode: transport.mode(),
        transport_healthy: transport.is_healthy(),
        public_endpoint: transport.public_endpoint().to_string(),
    })
}

fn validate_peer_readback(
    diagnostics: &WireGuardPeerDiagnostics,
    expected: &ParsedConfiguration,
    expected_wireguard_endpoint: SocketAddr,
) -> Result<(), TunnelError> {
    let expected_allowed_ips = expected
        .allowed_ips
        .iter()
        .map(ToString::to_string)
        .collect::<Vec<_>>();
    if diagnostics.peer_public_key != STANDARD.encode(expected.server_public_key)
        || diagnostics.endpoint != expected_wireguard_endpoint.to_string()
        || diagnostics.allowed_ips != expected_allowed_ips
        || !diagnostics
            .allowed_ips
            .iter()
            .any(|network| network == "0.0.0.0/0")
        || diagnostics.persistent_keepalive != KEEPALIVE_SECONDS
    {
        return Err(TunnelError::ConfigurationReadbackMismatch);
    }
    Ok(())
}

fn log_peer_diagnostics(stage: &str, diagnostics: &WireGuardPeerDiagnostics) {
    eprintln!(
        "wireguard_peer_diagnostics stage={stage} peer_public_key={} endpoint={} allowed_ips={:?} persistent_keepalive={} tx_bytes={} rx_bytes={} transport_mode={:?} transport_healthy={} public_endpoint={}",
        diagnostics.peer_public_key,
        diagnostics.endpoint,
        diagnostics.allowed_ips,
        diagnostics.persistent_keepalive,
        diagnostics.tx_bytes,
        diagnostics.rx_bytes,
        diagnostics.transport_mode,
        diagnostics.transport_healthy,
        diagnostics.public_endpoint,
    );
}

fn log_transport_diagnostics(stage: &str, transport: &ActivePacketTransport) {
    debug_log::event(
        "transport_diagnostics",
        format_args!(
            "stage={stage} mode={:?} healthy={} wireguard_endpoint={} public_endpoint={} counters={:?}",
            transport.mode(),
            transport.is_healthy(),
            transport.wireguard_endpoint(),
            transport.public_endpoint(),
            transport.snapshot()
        ),
    );
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
    debug_log::event(
        "endpoint_bypass_route_installed",
        format_args!(
            "endpoint={endpoint} physical_interface_index={}",
            existing_endpoint_route.InterfaceIndex
        ),
    );

    for (network, prefix) in FULL_TUNNEL_ROUTE_PREFIXES {
        let route = route_for_interface(adapter.get_luid(), network, prefix);
        if let Err(error) = install_route(route, &mut installed) {
            remove_routes(&installed);
            return Err(error);
        }
        debug_log::event(
            "full_tunnel_route_installed",
            format_args!("prefix={network}/{prefix}"),
        );
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
    debug_log::event(
        "route_cleanup_started",
        format_args!("tracked_routes={}", routes.len()),
    );
    for route in routes.iter().rev() {
        let _ = unsafe { DeleteIpForwardEntry2(route) };
    }
    debug_log::event("route_cleanup_finished", format_args!("result=attempted"));
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
    obfuscation: Option<ObfuscationConfig>,
    direct: bool,
    public_endpoint: SocketAddr,
    server_public_key: [u8; 32],
    client_address: IpNet,
    dns: Vec<IpAddr>,
    allowed_ips: Vec<IpNet>,
}

impl TryFrom<TunnelConfiguration> for ParsedConfiguration {
    type Error = TunnelError;

    fn try_from(value: TunnelConfiguration) -> Result<Self, Self::Error> {
        if let Some(config) = &value.obfuscation {
            packet_obfuscation::provider(config).map_err(|_| TunnelError::InvalidConfiguration)?;
            // 1280-byte IP MTU + 32-byte WireGuard data overhead + 8-byte framing.
            if value.direct || config.max_datagram_size < 1320 {
                return Err(TunnelError::InvalidConfiguration);
            }
        }
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
            obfuscation: value.obfuscation,
            direct: value.direct,
            public_endpoint: SocketAddr::new(IpAddr::V4(endpoint_ip), value.endpoint.port),
            server_public_key,
            client_address,
            dns,
            allowed_ips,
        })
    }
}

#[derive(Debug)]
enum TunnelError {
    RouteLeakDetected,
    InvalidConfiguration,
    TransportConfigurationInvalid,
    TransportUnavailable,
    ConfigurationReadbackMismatch,
    KeyMissing,
    KeyUnavailable,
    ComponentMissing,
    PrivilegesRequired,
    HandshakeTimeout,
    Unavailable,
}

impl TunnelError {
    fn code(&self) -> &'static str {
        match self {
            Self::RouteLeakDetected => "route_leak_detected",
            Self::InvalidConfiguration => "invalid_wireguard_configuration",
            Self::TransportConfigurationInvalid => "obfuscation_transport_configuration_invalid",
            Self::TransportUnavailable => "obfuscation_transport_unavailable",
            Self::ConfigurationReadbackMismatch => "wireguard_configuration_readback_mismatch",
            Self::KeyMissing => "wireguard_key_missing",
            Self::KeyUnavailable => "wireguard_key_storage_unavailable",
            Self::ComponentMissing => "wireguard_component_missing",
            Self::PrivilegesRequired => "administrator_privileges_required",
            Self::HandshakeTimeout => "wireguard_handshake_timeout",
            Self::Unavailable => "wireguard_tunnel_unavailable",
        }
    }
}

impl From<TransportError> for TunnelError {
    fn from(error: TransportError) -> Self {
        match error {
            TransportError::InvalidConfiguration => Self::TransportConfigurationInvalid,
            TransportError::Unavailable => Self::TransportUnavailable,
        }
    }
}

#[tauri::command]
pub fn start_wireguard_tunnel(
    configuration: TunnelConfiguration,
    tunnel: tauri::State<'_, WireGuardTunnelState>,
    keys: tauri::State<'_, WireGuardKeyState>,
) -> Result<TunnelStatus, &'static str> {
    debug_log::event(
        "native_connect_command_received",
        format_args!("command=start"),
    );
    match tunnel.start(configuration, &keys) {
        Ok(status) => Ok(status),
        Err(error) => {
            debug_log::event(
                "native_connect_command_failed",
                format_args!("error_code={}", error.code()),
            );
            Err(error.code())
        }
    }
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

#[tauri::command]
pub fn get_wireguard_peer_diagnostics(
    tunnel: tauri::State<'_, WireGuardTunnelState>,
) -> Result<Option<WireGuardPeerDiagnostics>, &'static str> {
    tunnel.diagnostics().map_err(|error| error.code())
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

fn wait_for_handshake(
    adapter: &Adapter,
    transport: &ActivePacketTransport,
) -> Result<(), TunnelError> {
    debug_log::event(
        "wireguard_handshake_wait_started",
        format_args!("timeout_ms={}", HANDSHAKE_TIMEOUT.as_millis()),
    );
    let socket = std::net::UdpSocket::bind((Ipv4Addr::UNSPECIFIED, 0))
        .map_err(|_| TunnelError::Unavailable)?;
    socket
        .send_to(&[0], (Ipv4Addr::new(1, 1, 1, 1), 9))
        .map_err(|_| TunnelError::Unavailable)?;

    let started = Instant::now();
    let mut last_report = Instant::now() - Duration::from_secs(1);
    let deadline = Instant::now() + HANDSHAKE_TIMEOUT;
    while Instant::now() < deadline {
        if !transport.is_healthy() {
            debug_log::event(
                "wireguard_handshake_wait_failed",
                format_args!(
                    "reason=transport_unhealthy counters={:?}",
                    transport.snapshot()
                ),
            );
            return Err(TunnelError::TransportUnavailable);
        }
        let configuration = adapter.get_config();
        let peer = configuration.peers.first();
        let handshake_observed = peer.is_some_and(|value| value.last_handshake.is_some());
        if last_report.elapsed() >= Duration::from_millis(500) {
            debug_log::event(
                "wireguard_handshake_poll",
                format_args!(
                    "elapsed_ms={} handshake={} tx_bytes={} rx_bytes={} transport_counters={:?}",
                    started.elapsed().as_millis(),
                    handshake_observed,
                    peer.map(|value| value.tx_bytes).unwrap_or_default(),
                    peer.map(|value| value.rx_bytes).unwrap_or_default(),
                    transport.snapshot()
                ),
            );
            last_report = Instant::now();
        }
        if handshake_observed {
            return Ok(());
        }
        thread::sleep(HANDSHAKE_POLL_INTERVAL);
    }
    debug_log::event(
        "wireguard_handshake_wait_failed",
        format_args!(
            "reason=timeout elapsed_ms={} transport_counters={:?}",
            started.elapsed().as_millis(),
            transport.snapshot()
        ),
    );
    Err(TunnelError::HandshakeTimeout)
}

#[tauri::command]
pub async fn verify_wireguard_internet(
    tunnel: tauri::State<'_, WireGuardTunnelState>,
) -> Result<crate::internet_verification::Verification, &'static str> {
    // Do not hold the adapter mutex during network I/O: disconnect must remain responsive.
    let context = {
        let active = tunnel.active.lock().map_err(|_| "UNKNOWN")?;
        active.as_ref().and_then(|tunnel| {
            (tunnel.transport.is_healthy() && tunnel.adapter.is_up().unwrap_or(false)).then(|| {
                crate::internet_verification::PathContext {
                    luid: tunnel.adapter.get_luid(),
                    source: tunnel.client_ip,
                    dns: tunnel.dns.clone(),
                }
            })
        })
    };
    let Some(context) = context else {
        return Ok(crate::internet_verification::Verification::failed(
            false,
            "HANDSHAKE_FAILED",
        ));
    };
    let result = tauri::async_runtime::spawn_blocking(move || {
        crate::internet_verification::verify(&context)
    })
    .await
    .map_err(|_| "UNKNOWN")?;
    if tunnel.status().map_err(|_| "UNKNOWN")? != TunnelStatus::Up {
        return Ok(crate::internet_verification::Verification::failed(
            false,
            "HANDSHAKE_FAILED",
        ));
    }
    Ok(result)
}

pub(crate) fn verification_route(address: IpAddr, luid: u64) -> Result<u32, &'static str> {
    #[cfg(windows)]
    {
        let route = best_ipv4_route(address).map_err(|_| "ROUTE_LEAK_DETECTED")?;
        let actual = unsafe { std::mem::transmute::<NET_LUID_LH, u64>(route.InterfaceLuid) };
        if actual != luid || route.InterfaceIndex == 0 {
            return Err("ROUTE_LEAK_DETECTED");
        }
        Ok(route.InterfaceIndex)
    }
    #[cfg(not(windows))]
    {
        let _ = (address, luid);
        Err("ROUTE_LEAK_DETECTED")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_configuration() -> TunnelConfiguration {
        TunnelConfiguration {
            obfuscation: None,
            direct: false,
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
    fn validates_obfuscation_at_native_boundary() {
        let mut configuration = valid_configuration();
        configuration.obfuscation = Some(ObfuscationConfig {
            mode: "SIMPLE_PACKET_WRAPPER_V1".into(),
            version: 1,
            max_datagram_size: 1320,
        });
        assert!(ParsedConfiguration::try_from(configuration).is_ok());
        let mut configuration = valid_configuration();
        configuration.obfuscation = Some(ObfuscationConfig {
            mode: "SIMPLE_PACKET_WRAPPER_V1".into(),
            version: 1,
            max_datagram_size: 1319,
        });
        assert!(ParsedConfiguration::try_from(configuration).is_err());
        let mut configuration = valid_configuration();
        configuration.direct = true;
        configuration.obfuscation = Some(ObfuscationConfig {
            mode: "SIMPLE_PACKET_WRAPPER_V1".into(),
            version: 1,
            max_datagram_size: 1400,
        });
        assert!(ParsedConfiguration::try_from(configuration).is_err());
    }

    #[test]
    fn explicit_udp_profile_preserves_direct_selection_and_configurable_port() {
        let mut configuration = valid_configuration();
        configuration.direct = true;
        configuration.endpoint.port = 443;
        let parsed = ParsedConfiguration::try_from(configuration).unwrap();
        assert!(parsed.direct);
        assert_eq!(parsed.public_endpoint.port(), 443);
        assert!(
            !ParsedConfiguration::try_from(valid_configuration())
                .unwrap()
                .direct
        );
    }

    #[test]
    fn accepts_complete_backend_transport_configuration() {
        let parsed = ParsedConfiguration::try_from(valid_configuration()).unwrap();
        assert_eq!(
            parsed.public_endpoint,
            "204.48.17.50:51820".parse().unwrap()
        );
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
            TunnelError::ComponentMissing.code(),
            "wireguard_component_missing"
        );
        assert_eq!(
            TunnelError::ConfigurationReadbackMismatch.code(),
            "wireguard_configuration_readback_mismatch"
        );
        assert_eq!(
            TunnelError::TransportConfigurationInvalid.code(),
            "obfuscation_transport_configuration_invalid"
        );
        assert_eq!(
            TunnelError::TransportUnavailable.code(),
            "obfuscation_transport_unavailable"
        );
    }

    #[test]
    fn validates_expected_wireguardnt_peer_readback() {
        let parsed = ParsedConfiguration::try_from(valid_configuration()).unwrap();
        let diagnostics = WireGuardPeerDiagnostics {
            peer_public_key: STANDARD.encode(parsed.server_public_key),
            endpoint: parsed.public_endpoint.to_string(),
            allowed_ips: vec!["0.0.0.0/0".into()],
            persistent_keepalive: KEEPALIVE_SECONDS,
            tx_bytes: 128,
            rx_bytes: 256,
            transport_mode: TransportMode::Direct,
            transport_healthy: true,
            public_endpoint: parsed.public_endpoint.to_string(),
        };

        assert!(validate_peer_readback(&diagnostics, &parsed, parsed.public_endpoint).is_ok());
    }

    #[test]
    fn rejects_wireguardnt_peer_readback_without_full_tunnel_allowed_ips() {
        let parsed = ParsedConfiguration::try_from(valid_configuration()).unwrap();
        let diagnostics = WireGuardPeerDiagnostics {
            peer_public_key: STANDARD.encode(parsed.server_public_key),
            endpoint: parsed.public_endpoint.to_string(),
            allowed_ips: vec!["10.77.0.0/16".into()],
            persistent_keepalive: KEEPALIVE_SECONDS,
            tx_bytes: 0,
            rx_bytes: 0,
            transport_mode: TransportMode::Direct,
            transport_healthy: true,
            public_endpoint: parsed.public_endpoint.to_string(),
        };

        assert_eq!(
            validate_peer_readback(&diagnostics, &parsed, parsed.public_endpoint)
                .unwrap_err()
                .code(),
            "wireguard_configuration_readback_mismatch"
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
