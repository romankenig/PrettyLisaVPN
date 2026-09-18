//! Native packet transport between WireGuardNT and the selected public endpoint.

use std::io;
use std::net::{IpAddr, Ipv4Addr, SocketAddr, UdpSocket};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::Duration;

use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use chacha20poly1305::aead::{Aead, KeyInit, Payload};
use chacha20poly1305::{ChaCha20Poly1305, Nonce};
use rand_core::{OsRng, RngCore};
use serde::Serialize;
use zeroize::{Zeroize, Zeroizing};

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
}

#[derive(Debug)]
pub(crate) enum TransportError {
    InvalidConfiguration,
    Unavailable,
}

enum TransportSelection {
    Direct,
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
    PrettyLisaV1(PrettyLisaV1Client),
}

impl ActivePacketTransport {
    pub(crate) fn start(public_endpoint: SocketAddr) -> Result<Self, TransportError> {
        Self::start_selected(public_endpoint, TransportSelection::from_environment()?)
    }

    fn start_selected(
        public_endpoint: SocketAddr,
        selection: TransportSelection,
    ) -> Result<Self, TransportError> {
        match selection {
            TransportSelection::Direct => Ok(Self::Direct { public_endpoint }),
            TransportSelection::PrettyLisaV1 { key, public_port } => {
                let public_endpoint = SocketAddr::new(public_endpoint.ip(), public_port);
                Ok(Self::PrettyLisaV1(PrettyLisaV1Client::start(
                    public_endpoint,
                    &key,
                )?))
            }
        }
    }

    pub(crate) fn wireguard_endpoint(&self) -> SocketAddr {
        match self {
            Self::Direct { public_endpoint } => *public_endpoint,
            Self::PrettyLisaV1(client) => client.local_endpoint,
        }
    }

    pub(crate) fn public_endpoint(&self) -> SocketAddr {
        match self {
            Self::Direct { public_endpoint } => *public_endpoint,
            Self::PrettyLisaV1(client) => client.public_endpoint,
        }
    }

    pub(crate) fn mode(&self) -> TransportMode {
        match self {
            Self::Direct { .. } => TransportMode::Direct,
            Self::PrettyLisaV1(_) => TransportMode::PrettyLisaV1,
        }
    }

    pub(crate) fn is_healthy(&self) -> bool {
        match self {
            Self::Direct { .. } => true,
            Self::PrettyLisaV1(client) => client.healthy.load(Ordering::Acquire),
        }
    }

    pub(crate) fn stop(&mut self) {
        if let Self::PrettyLisaV1(client) = self {
            client.stop();
        }
    }
}

impl Drop for ActivePacketTransport {
    fn drop(&mut self) {
        self.stop();
    }
}

pub(crate) struct PrettyLisaV1Client {
    local_endpoint: SocketAddr,
    public_endpoint: SocketAddr,
    stop_requested: Arc<AtomicBool>,
    healthy: Arc<AtomicBool>,
    worker: Option<JoinHandle<()>>,
}

impl PrettyLisaV1Client {
    fn start(public_endpoint: SocketAddr, key: &[u8; KEY_SIZE]) -> Result<Self, TransportError> {
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

        let stop_requested = Arc::new(AtomicBool::new(false));
        let healthy = Arc::new(AtomicBool::new(true));
        let worker_stop = Arc::clone(&stop_requested);
        let worker_health = Arc::clone(&healthy);
        let codec = V1PacketCodec::new(key);
        let worker = thread::Builder::new()
            .name("prettylisa-obfuscation-v1".to_owned())
            .spawn(move || {
                run_forwarder(
                    local_socket,
                    public_socket,
                    codec,
                    &worker_stop,
                    &worker_health,
                );
            })
            .map_err(|_| TransportError::Unavailable)?;

        Ok(Self {
            local_endpoint,
            public_endpoint,
            stop_requested,
            healthy,
            worker: Some(worker),
        })
    }

    fn stop(&mut self) {
        self.stop_requested.store(true, Ordering::Release);
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
        self.healthy.store(false, Ordering::Release);
    }
}

impl Drop for PrettyLisaV1Client {
    fn drop(&mut self) {
        self.stop();
    }
}

fn run_forwarder(
    local_socket: UdpSocket,
    public_socket: UdpSocket,
    codec: V1PacketCodec,
    stop_requested: &AtomicBool,
    healthy: &AtomicBool,
) {
    let mut local_buffer = [0_u8; MAX_PACKET_SIZE + 1];
    let mut public_buffer = [0_u8; MAX_ENVELOPE_SIZE + 1];
    let mut wireguard_endpoint: Option<SocketAddr> = None;
    while !stop_requested.load(Ordering::Acquire) {
        match local_socket.recv_from(&mut local_buffer) {
            Ok((size, endpoint)) => {
                if !endpoint.ip().is_loopback() || size == 0 || size > MAX_PACKET_SIZE {
                    continue;
                }
                wireguard_endpoint = Some(endpoint);
                match codec.encode(&local_buffer[..size]) {
                    Ok(encoded) if public_socket.send(&encoded).is_ok() => {}
                    Ok(_) | Err(_) => {
                        healthy.store(false, Ordering::Release);
                        return;
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
                let Some(endpoint) = wireguard_endpoint else {
                    continue;
                };
                if let Ok(decoded) = codec.decode(&public_buffer[..size]) {
                    if local_socket.send_to(&decoded, endpoint).is_err() {
                        healthy.store(false, Ordering::Release);
                        return;
                    }
                }
            }
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {}
            Err(_) => {
                healthy.store(false, Ordering::Release);
                return;
            }
        }
        thread::sleep(IO_POLL_INTERVAL);
    }
    healthy.store(false, Ordering::Release);
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
        let mut client = PrettyLisaV1Client::start(public_endpoint, &key).unwrap();
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

        let response = codec
            .encode_with(b"reply", [8_u8; NONCE_SIZE], &[2_u8; 3])
            .unwrap();
        server.send_to(&response, client_endpoint).unwrap();
        let (size, source) = wireguard.recv_from(&mut buffer).unwrap();
        assert_eq!(&buffer[..size], b"reply");
        assert_eq!(source, local_endpoint);
        assert!(client.healthy.load(Ordering::Acquire));

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
            let client = PrettyLisaV1Client::start(endpoint, &key).unwrap();
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
