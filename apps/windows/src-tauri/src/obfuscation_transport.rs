//! Native packet transport between WireGuardNT and the selected public endpoint.

use std::io;
use std::net::{IpAddr, Ipv4Addr, SocketAddr, UdpSocket};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use chacha20poly1305::aead::{Aead, KeyInit, Payload};
use chacha20poly1305::{ChaCha20Poly1305, Nonce};
use rand_core::{OsRng, RngCore};
use serde::Serialize;
use zeroize::{Zeroize, Zeroizing};

use crate::debug_log;
use crate::packet_obfuscation::{self, ObfuscationConfig, ObfuscationProvider, PacketError};

const PROTOCOL_VERSION: u8 = 1;
const KEY_SIZE: usize = 32;
const NONCE_SIZE: usize = 12;
const TAG_SIZE: usize = 16;
const LENGTH_SIZE: usize = 2;
const HEADER_SIZE: usize = 1 + NONCE_SIZE;
const MAX_PACKET_SIZE: usize = 4_096;
const MAX_PADDING_SIZE: usize = 255;
const MAX_ENVELOPE_SIZE: usize =
    HEADER_SIZE + LENGTH_SIZE + MAX_PACKET_SIZE + MAX_PADDING_SIZE + TAG_SIZE;
const IO_POLL_INTERVAL: Duration = Duration::from_millis(1);
const TRANSPORT_MODE_ENV: &str = "PRETTYLISA_VPN_TRANSPORT_MODE";
const TRANSPORT_SECRET_ENV: &str = "PRETTYLISA_V1_SECRET";
const TRANSPORT_PUBLIC_PORT_ENV: &str = "PRETTYLISA_V1_PUBLIC_PORT";
const DEFAULT_TRANSPORT_PUBLIC_PORT: u16 = 443;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub(crate) enum TransportMode {
    Direct,
    PrettyLisaV1,
    WgObfuscator,
    PacketWrapped,
}

#[derive(Debug)]
pub(crate) enum TransportError {
    InvalidConfiguration,
    Unavailable,
}

enum TransportSelection {
    Direct,
    WgObfuscator,
    PrettyLisaV1 {
        key: Zeroizing<[u8; KEY_SIZE]>,
        public_port: u16,
    },
}

impl TransportSelection {
    fn from_environment() -> Result<Self, TransportError> {
        let mode = std::env::var(TRANSPORT_MODE_ENV).unwrap_or_else(|_| "DIRECT".to_owned());
        let secret = std::env::var(TRANSPORT_SECRET_ENV).ok().map(Zeroizing::new);
        let public_port = std::env::var(TRANSPORT_PUBLIC_PORT_ENV).ok();
        Self::from_values(
            &mode,
            secret.as_ref().map(|value| value.as_str()),
            public_port.as_deref(),
        )
    }

    fn from_values(
        mode: &str,
        secret: Option<&str>,
        public_port: Option<&str>,
    ) -> Result<Self, TransportError> {
        match mode {
            "DIRECT" => Ok(Self::Direct),
            "WG_OBFUSCATOR" => Ok(Self::WgObfuscator),
            "PRETTYLISA_V1" => {
                let encoded = secret.ok_or(TransportError::InvalidConfiguration)?;
                let mut decoded = STANDARD
                    .decode(encoded)
                    .map_err(|_| TransportError::InvalidConfiguration)?;
                if decoded.len() != KEY_SIZE || STANDARD.encode(&decoded) != encoded {
                    decoded.zeroize();
                    return Err(TransportError::InvalidConfiguration);
                }
                let mut key = Zeroizing::new([0_u8; KEY_SIZE]);
                key.copy_from_slice(&decoded);
                decoded.zeroize();
                let public_port = match public_port {
                    Some(value) => value
                        .parse::<u16>()
                        .map_err(|_| TransportError::InvalidConfiguration)?,
                    None => DEFAULT_TRANSPORT_PUBLIC_PORT,
                };
                if public_port == 0 {
                    return Err(TransportError::InvalidConfiguration);
                }
                Ok(Self::PrettyLisaV1 { key, public_port })
            }
            _ => Err(TransportError::InvalidConfiguration),
        }
    }
}

pub(crate) enum ActivePacketTransport {
    Direct { public_endpoint: SocketAddr },
    WgObfuscator(crate::wg_obfuscator::Client),
    PrettyLisaV1(PacketRelayClient),
    PacketWrapped(PacketRelayClient),
}

impl ActivePacketTransport {
    pub(crate) fn start_configured(
        public_endpoint: SocketAddr,
        config: &ObfuscationConfig,
    ) -> Result<Self, TransportError> {
        let codec = packet_obfuscation::provider(config)
            .map_err(|_| TransportError::InvalidConfiguration)?;
        if config.mode == "NONE" {
            return Ok(Self::Direct { public_endpoint });
        }
        Ok(Self::PacketWrapped(PacketRelayClient::start_with_provider(
            public_endpoint,
            codec,
        )?))
    }

    pub(crate) fn start(public_endpoint: SocketAddr) -> Result<Self, TransportError> {
        debug_log::event(
            "transport_selection_started",
            format_args!("backend_endpoint={public_endpoint}"),
        );
        let transport =
            Self::start_selected(public_endpoint, TransportSelection::from_environment()?)?;
        debug_log::event(
            "transport_ready",
            format_args!(
                "mode={:?} wireguard_endpoint={} public_endpoint={} healthy={}",
                transport.mode(),
                transport.wireguard_endpoint(),
                transport.public_endpoint(),
                transport.is_healthy()
            ),
        );
        Ok(transport)
    }

    fn start_selected(
        public_endpoint: SocketAddr,
        selection: TransportSelection,
    ) -> Result<Self, TransportError> {
        match selection {
            TransportSelection::Direct => Ok(Self::Direct { public_endpoint }),
            TransportSelection::WgObfuscator => Ok(Self::WgObfuscator(
                crate::wg_obfuscator::Client::start(public_endpoint)?,
            )),
            TransportSelection::PrettyLisaV1 { key, public_port } => {
                let public_endpoint = SocketAddr::new(public_endpoint.ip(), public_port);
                Ok(Self::PrettyLisaV1(PacketRelayClient::start(
                    public_endpoint,
                    &key,
                )?))
            }
        }
    }

    pub(crate) fn wireguard_endpoint(&self) -> SocketAddr {
        match self {
            Self::Direct { public_endpoint } => *public_endpoint,
            Self::WgObfuscator(client) => client.local_endpoint,
            Self::PrettyLisaV1(client) | Self::PacketWrapped(client) => client.local_endpoint,
        }
    }

    pub(crate) fn public_endpoint(&self) -> SocketAddr {
        match self {
            Self::Direct { public_endpoint } => *public_endpoint,
            Self::WgObfuscator(client) => client.public_endpoint,
            Self::PrettyLisaV1(client) | Self::PacketWrapped(client) => client.public_endpoint,
        }
    }

    pub(crate) fn mode(&self) -> TransportMode {
        match self {
            Self::Direct { .. } => TransportMode::Direct,
            Self::WgObfuscator(_) => TransportMode::WgObfuscator,
            Self::PrettyLisaV1(_) => TransportMode::PrettyLisaV1,
            Self::PacketWrapped(_) => TransportMode::PacketWrapped,
        }
    }

    pub(crate) fn is_healthy(&self) -> bool {
        match self {
            Self::Direct { .. } => true,
            Self::WgObfuscator(client) => client.is_healthy(),
            Self::PrettyLisaV1(client) | Self::PacketWrapped(client) => {
                client.healthy.load(Ordering::Acquire)
            }
        }
    }

    pub(crate) fn snapshot(&self) -> Option<TransportSnapshot> {
        match self {
            Self::Direct { .. } | Self::WgObfuscator(_) => None,
            Self::PrettyLisaV1(client) | Self::PacketWrapped(client) => {
                Some(client.counters.snapshot())
            }
        }
    }

    pub(crate) fn stop(&mut self) {
        debug_log::event(
            "transport_stop_requested",
            format_args!("mode={:?} counters={:?}", self.mode(), self.snapshot()),
        );
        if let Self::PrettyLisaV1(client) | Self::PacketWrapped(client) = self {
            client.stop();
        }
        if let Self::WgObfuscator(client) = self {
            client.stop();
        }
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) struct TransportSnapshot {
    pub(crate) inner_tx_packets: u64,
    pub(crate) inner_tx_bytes: u64,
    pub(crate) public_tx_packets: u64,
    pub(crate) public_tx_bytes: u64,
    pub(crate) public_rx_packets: u64,
    pub(crate) public_rx_bytes: u64,
    pub(crate) inner_rx_packets: u64,
    pub(crate) inner_rx_bytes: u64,
    pub(crate) rejected_public_packets: u64,
}

#[derive(Default)]
struct TransportCounters {
    inner_tx_packets: AtomicU64,
    inner_tx_bytes: AtomicU64,
    public_tx_packets: AtomicU64,
    public_tx_bytes: AtomicU64,
    public_rx_packets: AtomicU64,
    public_rx_bytes: AtomicU64,
    inner_rx_packets: AtomicU64,
    inner_rx_bytes: AtomicU64,
    rejected_public_packets: AtomicU64,
}

impl TransportCounters {
    fn snapshot(&self) -> TransportSnapshot {
        TransportSnapshot {
            inner_tx_packets: self.inner_tx_packets.load(Ordering::Relaxed),
            inner_tx_bytes: self.inner_tx_bytes.load(Ordering::Relaxed),
            public_tx_packets: self.public_tx_packets.load(Ordering::Relaxed),
            public_tx_bytes: self.public_tx_bytes.load(Ordering::Relaxed),
            public_rx_packets: self.public_rx_packets.load(Ordering::Relaxed),
            public_rx_bytes: self.public_rx_bytes.load(Ordering::Relaxed),
            inner_rx_packets: self.inner_rx_packets.load(Ordering::Relaxed),
            inner_rx_bytes: self.inner_rx_bytes.load(Ordering::Relaxed),
            rejected_public_packets: self.rejected_public_packets.load(Ordering::Relaxed),
        }
    }
}

impl Drop for ActivePacketTransport {
    fn drop(&mut self) {
        self.stop();
    }
}

pub(crate) struct PacketRelayClient {
    local_endpoint: SocketAddr,
    public_endpoint: SocketAddr,
    stop_requested: Arc<AtomicBool>,
    healthy: Arc<AtomicBool>,
    counters: Arc<TransportCounters>,
    worker: Option<JoinHandle<()>>,
}

impl PacketRelayClient {
    fn start(public_endpoint: SocketAddr, key: &[u8; KEY_SIZE]) -> Result<Self, TransportError> {
        Self::start_with_provider(public_endpoint, Box::new(V1PacketCodec::new(key)))
    }

    fn start_with_provider(
        public_endpoint: SocketAddr,
        codec: Box<dyn ObfuscationProvider>,
    ) -> Result<Self, TransportError> {
        if !matches!(public_endpoint.ip(), IpAddr::V4(address) if !address.is_unspecified()) {
            return Err(TransportError::InvalidConfiguration);
        }
        let local_socket =
            UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).map_err(|_| TransportError::Unavailable)?;
        let local_endpoint = local_socket
            .local_addr()
            .map_err(|_| TransportError::Unavailable)?;
        let public_socket =
            UdpSocket::bind((Ipv4Addr::UNSPECIFIED, 0)).map_err(|_| TransportError::Unavailable)?;
        public_socket
            .connect(public_endpoint)
            .map_err(|_| TransportError::Unavailable)?;
        local_socket
            .set_nonblocking(true)
            .map_err(|_| TransportError::Unavailable)?;
        public_socket
            .set_nonblocking(true)
            .map_err(|_| TransportError::Unavailable)?;

        let public_local_endpoint = public_socket
            .local_addr()
            .map_err(|_| TransportError::Unavailable)?;
        debug_log::event(
            "obfuscation_socket_bound",
            format_args!(
                "local_listener={local_endpoint} public_socket={public_local_endpoint} public_endpoint={public_endpoint}"
            ),
        );

        let stop_requested = Arc::new(AtomicBool::new(false));
        let healthy = Arc::new(AtomicBool::new(true));
        let counters = Arc::new(TransportCounters::default());
        let worker_stop = Arc::clone(&stop_requested);
        let worker_health = Arc::clone(&healthy);
        let worker_counters = Arc::clone(&counters);
        let worker = thread::Builder::new()
            .name("prettylisa-obfuscation-v1".to_owned())
            .spawn(move || {
                run_forwarder(
                    local_socket,
                    public_socket,
                    codec,
                    &worker_stop,
                    &worker_health,
                    &worker_counters,
                );
            })
            .map_err(|_| TransportError::Unavailable)?;

        Ok(Self {
            local_endpoint,
            public_endpoint,
            stop_requested,
            healthy,
            counters,
            worker: Some(worker),
        })
    }

    fn stop(&mut self) {
        self.stop_requested.store(true, Ordering::Release);
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
        self.healthy.store(false, Ordering::Release);
        debug_log::event(
            "obfuscation_transport_stopped",
            format_args!("counters={:?}", self.counters.snapshot()),
        );
    }
}

impl Drop for PacketRelayClient {
    fn drop(&mut self) {
        self.stop();
    }
}

fn run_forwarder(
    local_socket: UdpSocket,
    public_socket: UdpSocket,
    codec: Box<dyn ObfuscationProvider>,
    stop_requested: &AtomicBool,
    healthy: &AtomicBool,
    counters: &TransportCounters,
) {
    let mut local_buffer = [0_u8; 65_536];
    let mut public_buffer = [0_u8; 65_536];
    let mut wireguard_endpoint: Option<SocketAddr> = None;
    let mut last_report = Instant::now();
    debug_log::event(
        "obfuscation_worker_started",
        format_args!("protocol_version=1"),
    );
    while !stop_requested.load(Ordering::Acquire) {
        match local_socket.recv_from(&mut local_buffer) {
            Ok((size, endpoint)) => {
                if !endpoint.ip().is_loopback() || size == 0 {
                    continue;
                }
                wireguard_endpoint = Some(endpoint);
                counters.inner_tx_packets.fetch_add(1, Ordering::Relaxed);
                counters
                    .inner_tx_bytes
                    .fetch_add(size as u64, Ordering::Relaxed);
                match codec.encode(&local_buffer[..size]) {
                    Ok(encoded) => match public_socket.send(&encoded) {
                        Ok(sent) if sent == encoded.len() => {
                            counters.public_tx_packets.fetch_add(1, Ordering::Relaxed);
                            counters
                                .public_tx_bytes
                                .fetch_add(sent as u64, Ordering::Relaxed);
                        }
                        Ok(_) | Err(_) => {
                            debug_log::event(
                                "obfuscation_public_send_failed",
                                format_args!("counters={:?}", counters.snapshot()),
                            );
                            healthy.store(false, Ordering::Release);
                            return;
                        }
                    },
                    Err(_) => {
                        debug_log::event(
                            "obfuscation_encode_failed",
                            format_args!("inner_size={size} counters={:?}", counters.snapshot()),
                        );
                        // Oversized/malformed local packets are dropped without killing the relay.
                    }
                }
            }
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {}
            Err(_) => {
                healthy.store(false, Ordering::Release);
                return;
            }
        }

        match public_socket.recv(&mut public_buffer) {
            Ok(size) => {
                counters.public_rx_packets.fetch_add(1, Ordering::Relaxed);
                counters
                    .public_rx_bytes
                    .fetch_add(size as u64, Ordering::Relaxed);
                let Some(endpoint) = wireguard_endpoint else {
                    continue;
                };
                match codec.decode(&public_buffer[..size]) {
                    Ok(decoded) => match local_socket.send_to(&decoded, endpoint) {
                        Ok(sent) if sent == decoded.len() => {
                            counters.inner_rx_packets.fetch_add(1, Ordering::Relaxed);
                            counters
                                .inner_rx_bytes
                                .fetch_add(sent as u64, Ordering::Relaxed);
                        }
                        Ok(_) | Err(_) => {
                            debug_log::event(
                                "obfuscation_local_reply_failed",
                                format_args!("counters={:?}", counters.snapshot()),
                            );
                            healthy.store(false, Ordering::Release);
                            return;
                        }
                    },
                    Err(error) => {
                        counters
                            .rejected_public_packets
                            .fetch_add(1, Ordering::Relaxed);
                        debug_log::event(
                            "obfuscation_decode_rejected",
                            format_args!(
                                "reason={error:?} envelope_size={size} counters={:?}",
                                counters.snapshot()
                            ),
                        );
                    }
                }
            }
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {}
            Err(_) => {
                healthy.store(false, Ordering::Release);
                return;
            }
        }
        if last_report.elapsed() >= Duration::from_secs(1) {
            let snapshot = counters.snapshot();
            if snapshot.inner_tx_packets > 0 || snapshot.public_rx_packets > 0 {
                debug_log::event(
                    "obfuscation_flow_snapshot",
                    format_args!(
                        "healthy={} counters={snapshot:?}",
                        healthy.load(Ordering::Acquire)
                    ),
                );
            }
            last_report = Instant::now();
        }
        thread::sleep(IO_POLL_INTERVAL);
    }
    healthy.store(false, Ordering::Release);
    debug_log::event(
        "obfuscation_worker_finished",
        format_args!("counters={:?}", counters.snapshot()),
    );
}

#[derive(Debug, PartialEq, Eq)]
enum CodecError {
    Malformed,
    UnsupportedVersion,
    Authentication,
    Oversized,
}

struct V1PacketCodec {
    cipher: ChaCha20Poly1305,
}

impl ObfuscationProvider for V1PacketCodec {
    fn encode(&self, packet: &[u8]) -> Result<Vec<u8>, PacketError> {
        V1PacketCodec::encode(self, packet).map_err(|_| PacketError::Malformed)
    }
    fn decode(&self, packet: &[u8]) -> Result<Vec<u8>, PacketError> {
        V1PacketCodec::decode(self, packet).map_err(|_| PacketError::Malformed)
    }
}

impl V1PacketCodec {
    fn new(key: &[u8; KEY_SIZE]) -> Self {
        Self {
            cipher: ChaCha20Poly1305::new(key.into()),
        }
    }

    fn encode(&self, packet: &[u8]) -> Result<Vec<u8>, CodecError> {
        if packet.is_empty() {
            return Err(CodecError::Malformed);
        }
        if packet.len() > MAX_PACKET_SIZE {
            return Err(CodecError::Oversized);
        }
        let padding_size = (OsRng.next_u32() as usize) % (MAX_PADDING_SIZE + 1);
        let mut nonce = [0_u8; NONCE_SIZE];
        OsRng.fill_bytes(&mut nonce);
        let mut padding = vec![0_u8; padding_size];
        OsRng.fill_bytes(&mut padding);
        self.encode_with(packet, nonce, &padding)
    }

    fn encode_with(
        &self,
        packet: &[u8],
        nonce: [u8; NONCE_SIZE],
        padding: &[u8],
    ) -> Result<Vec<u8>, CodecError> {
        if packet.is_empty() {
            return Err(CodecError::Malformed);
        }
        if packet.len() > MAX_PACKET_SIZE || padding.len() > MAX_PADDING_SIZE {
            return Err(CodecError::Oversized);
        }
        let mut plaintext = Vec::with_capacity(LENGTH_SIZE + packet.len() + padding.len());
        plaintext.extend_from_slice(&(packet.len() as u16).to_be_bytes());
        plaintext.extend_from_slice(packet);
        plaintext.extend_from_slice(padding);
        let ciphertext = self
            .cipher
            .encrypt(
                Nonce::from_slice(&nonce),
                Payload {
                    msg: &plaintext,
                    aad: &[PROTOCOL_VERSION],
                },
            )
            .map_err(|_| CodecError::Authentication)?;
        plaintext.zeroize();
        let mut encoded = Vec::with_capacity(HEADER_SIZE + ciphertext.len());
        encoded.push(PROTOCOL_VERSION);
        encoded.extend_from_slice(&nonce);
        encoded.extend_from_slice(&ciphertext);
        Ok(encoded)
    }

    fn decode(&self, packet: &[u8]) -> Result<Vec<u8>, CodecError> {
        if packet.len() < HEADER_SIZE + LENGTH_SIZE + 1 + TAG_SIZE {
            return Err(CodecError::Malformed);
        }
        if packet.len() > MAX_ENVELOPE_SIZE {
            return Err(CodecError::Oversized);
        }
        if packet[0] != PROTOCOL_VERSION {
            return Err(CodecError::UnsupportedVersion);
        }
        let nonce = Nonce::from_slice(&packet[1..HEADER_SIZE]);
        let mut plaintext = self
            .cipher
            .decrypt(
                nonce,
                Payload {
                    msg: &packet[HEADER_SIZE..],
                    aad: &packet[..1],
                },
            )
            .map_err(|_| CodecError::Authentication)?;
        if plaintext.len() < LENGTH_SIZE + 1 {
            plaintext.zeroize();
            return Err(CodecError::Malformed);
        }
        let packet_size = u16::from_be_bytes([plaintext[0], plaintext[1]]) as usize;
        if packet_size == 0 {
            plaintext.zeroize();
            return Err(CodecError::Malformed);
        }
        if packet_size > MAX_PACKET_SIZE {
            plaintext.zeroize();
            return Err(CodecError::Oversized);
        }
        let packet_end = LENGTH_SIZE + packet_size;
        if packet_end > plaintext.len() {
            plaintext.zeroize();
            return Err(CodecError::Malformed);
        }
        let decoded = plaintext[LENGTH_SIZE..packet_end].to_vec();
        plaintext.zeroize();
        Ok(decoded)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const COMPATIBILITY_PACKET_HEX: &str = "010000005072657474794c6973612d7631";
    const COMPATIBILITY_ENVELOPE_HEX: &str = concat!(
        "01a0a1a2a3a4a5a6a7a8a9aaab0cba795f4de692dfc57b876db0938e9ab0",
        "28e24fb2989357412e2cd8a5a754bed05f8bc4bd651e9b7b96a0"
    );

    #[test]
    fn wrapper_udp_loss_malformed_mtu_and_reconnect() {
        let server = UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        server
            .set_read_timeout(Some(Duration::from_secs(2)))
            .unwrap();
        let config = ObfuscationConfig {
            mode: "SIMPLE_PACKET_WRAPPER_V1".into(),
            version: 1,
            max_datagram_size: 1400,
        };
        let codec = packet_obfuscation::provider(&config).unwrap();
        for _ in 0..2 {
            let mut client =
                ActivePacketTransport::start_configured(server.local_addr().unwrap(), &config)
                    .unwrap();
            let vpn = UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
            vpn.set_read_timeout(Some(Duration::from_secs(2))).unwrap();
            let mut wire = [0u8; 65536];
            vpn.send_to(b"lost-packet", client.wireguard_endpoint())
                .unwrap();
            let (_, remote) = server.recv_from(&mut wire).unwrap(); // intentionally drop
            server.send_to(b"malformed-frame", remote).unwrap();
            // Oversized local packets must be dropped without stopping the relay.
            vpn.send_to(&vec![0; 1393], client.wireguard_endpoint())
                .unwrap();
            let packet = vec![37; 1392];
            vpn.send_to(&packet, client.wireguard_endpoint()).unwrap();
            let (size, remote) = server.recv_from(&mut wire).unwrap();
            assert_eq!(size, 1400);
            assert_eq!(codec.decode(&wire[..size]).unwrap(), packet);
            server.send_to(&wire[..size], remote).unwrap();
            let (size, _) = vpn.recv_from(&mut wire).unwrap();
            assert_eq!(&wire[..size], packet.as_slice());
            assert!(client.is_healthy());
            client.stop();
            assert!(!client.is_healthy());
        }
    }

    #[test]
    fn matches_stage_3ab_python_compatibility_vector() {
        let key = std::array::from_fn(|index| index as u8);
        let nonce = std::array::from_fn(|index| 0xa0 + index as u8);
        let padding = (0xf0..=0xf7).collect::<Vec<_>>();
        let packet = decode_hex(COMPATIBILITY_PACKET_HEX);
        let codec = V1PacketCodec::new(&key);

        let encoded = codec.encode_with(&packet, nonce, &padding).unwrap();

        assert_eq!(encode_hex(&encoded), COMPATIBILITY_ENVELOPE_HEX);
        assert_eq!(codec.decode(&encoded).unwrap(), packet);
    }

    #[test]
    fn rejects_failed_authentication_and_invalid_version() {
        let codec = V1PacketCodec::new(&[9_u8; KEY_SIZE]);
        let mut encoded = codec
            .encode_with(b"packet", [7_u8; NONCE_SIZE], &[3_u8; 4])
            .unwrap();
        encoded[HEADER_SIZE] ^= 1;
        assert_eq!(codec.decode(&encoded), Err(CodecError::Authentication));

        encoded[0] = 2;
        assert_eq!(codec.decode(&encoded), Err(CodecError::UnsupportedVersion));
    }

    #[test]
    fn selects_direct_or_v1_without_exposing_secret() {
        assert!(matches!(
            TransportSelection::from_values("DIRECT", None, None).unwrap(),
            TransportSelection::Direct
        ));
        let secret = STANDARD.encode([4_u8; KEY_SIZE]);
        assert!(matches!(
            TransportSelection::from_values("PRETTYLISA_V1", Some(&secret), None).unwrap(),
            TransportSelection::PrettyLisaV1 {
                public_port: DEFAULT_TRANSPORT_PUBLIC_PORT,
                ..
            }
        ));
        assert!(matches!(
            TransportSelection::from_values("PRETTYLISA_V1", Some(&secret), Some("8443")).unwrap(),
            TransportSelection::PrettyLisaV1 {
                public_port: 8443,
                ..
            }
        ));
        assert!(TransportSelection::from_values("PRETTYLISA_V1", None, None).is_err());
        assert!(
            TransportSelection::from_values("PRETTYLISA_V1", Some(&secret), Some("0")).is_err()
        );
        assert!(TransportSelection::from_values("UNKNOWN", Some(&secret), None).is_err());
    }

    #[test]
    fn v1_transport_maps_local_wireguard_to_public_endpoint_and_stops() {
        let key = [5_u8; KEY_SIZE];
        let server = UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        server
            .set_read_timeout(Some(Duration::from_secs(2)))
            .unwrap();
        let public_endpoint = server.local_addr().unwrap();
        let mut client = PacketRelayClient::start(public_endpoint, &key).unwrap();
        let local_endpoint = client.local_endpoint;
        let wireguard = UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        wireguard
            .set_read_timeout(Some(Duration::from_secs(2)))
            .unwrap();

        wireguard.send_to(b"wireguard", local_endpoint).unwrap();
        let mut buffer = [0_u8; MAX_ENVELOPE_SIZE];
        let (size, client_endpoint) = server.recv_from(&mut buffer).unwrap();
        let codec = V1PacketCodec::new(&key);
        assert_eq!(codec.decode(&buffer[..size]).unwrap(), b"wireguard");

        server
            .send_to(b"invalid-envelope", client_endpoint)
            .unwrap();
        let response = codec
            .encode_with(b"reply", [8_u8; NONCE_SIZE], &[2_u8; 3])
            .unwrap();
        server.send_to(&response, client_endpoint).unwrap();
        let (size, source) = wireguard.recv_from(&mut buffer).unwrap();
        assert_eq!(&buffer[..size], b"reply");
        assert_eq!(source, local_endpoint);
        assert!(client.healthy.load(Ordering::Acquire));
        // recv_from may finish before the worker updates its post-send counters.
        // Join before taking the final snapshot instead of depending on scheduling.
        client.stop();
        let snapshot = client.counters.snapshot();
        assert_eq!(snapshot.inner_tx_packets, 1);
        assert_eq!(snapshot.public_tx_packets, 1);
        assert_eq!(snapshot.public_rx_packets, 2);
        assert_eq!(snapshot.inner_rx_packets, 1);
        assert_eq!(snapshot.rejected_public_packets, 1);

        client.stop();
        assert!(!client.healthy.load(Ordering::Acquire));
        UdpSocket::bind(local_endpoint).expect("local relay socket must be released after stop");
    }

    #[test]
    fn v1_uses_transport_port_while_direct_preserves_wireguard_endpoint() {
        let wireguard_endpoint: SocketAddr = "127.0.0.1:51820".parse().unwrap();
        let direct =
            ActivePacketTransport::start_selected(wireguard_endpoint, TransportSelection::Direct)
                .unwrap();
        assert_eq!(direct.public_endpoint(), wireguard_endpoint);
        assert_eq!(direct.wireguard_endpoint(), wireguard_endpoint);

        let server = UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let expected_public_endpoint = server.local_addr().unwrap();
        let mut obfuscated = ActivePacketTransport::start_selected(
            wireguard_endpoint,
            TransportSelection::PrettyLisaV1 {
                key: Zeroizing::new([5_u8; KEY_SIZE]),
                public_port: expected_public_endpoint.port(),
            },
        )
        .unwrap();
        assert_eq!(obfuscated.public_endpoint(), expected_public_endpoint);
        assert!(obfuscated.wireguard_endpoint().ip().is_loopback());
        assert_ne!(obfuscated.wireguard_endpoint(), wireguard_endpoint);
        obfuscated.stop();
    }

    #[test]
    fn failed_setup_releases_local_transport() {
        let key = [6_u8; KEY_SIZE];
        let server = UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let endpoint = server.local_addr().unwrap();
        let local_endpoint = {
            let client = PacketRelayClient::start(endpoint, &key).unwrap();
            client.local_endpoint
        };

        UdpSocket::bind(local_endpoint)
            .expect("failed connection cleanup must release relay socket");
    }

    fn decode_hex(value: &str) -> Vec<u8> {
        value
            .as_bytes()
            .chunks_exact(2)
            .map(|chunk| u8::from_str_radix(std::str::from_utf8(chunk).unwrap(), 16).unwrap())
            .collect()
    }

    fn encode_hex(value: &[u8]) -> String {
        value.iter().map(|byte| format!("{byte:02x}")).collect()
    }
}
