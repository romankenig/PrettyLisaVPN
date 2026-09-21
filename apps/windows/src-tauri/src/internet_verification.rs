//! Independent, interface-pinned DNS + HTTPS health checks. Never log probe data.
use hickory_proto::op::{Message, MessageType, Query, ResponseCode};
use hickory_proto::rr::{Name, RData, RecordType};
use rustls::{ClientConfig, ClientConnection, RootCertStore, StreamOwned};
use serde::{Deserialize, Serialize};
use socket2::{Domain, Protocol, Socket, Type};
use std::io::{Read, Write};
use std::net::{IpAddr, SocketAddr, TcpStream, UdpSocket};
use std::sync::Arc;
use std::time::{Duration, Instant};
use url::Url;

type Check<T> = Result<T, &'static str>;
const MAX_RESPONSE: usize = 16_384;

pub struct PathContext {
    pub luid: u64,
    pub source: IpAddr,
    pub dns: Vec<IpAddr>,
}
#[derive(Debug, Serialize)]
pub struct Verification {
    tunnel_established: bool,
    internet_verified: bool,
    failure_code: Option<&'static str>,
    public_egress_ip: Option<IpAddr>,
}
impl Verification {
    pub fn failed(tunnel: bool, code: &'static str) -> Self {
        Self {
            tunnel_established: tunnel,
            internet_verified: false,
            failure_code: Some(code),
            public_egress_ip: None,
        }
    }
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Endpoint {
    url: String,
    expected_status: u16,
    #[serde(default)]
    expected_body: Option<String>,
    #[serde(default)]
    public_ip_body: bool,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Settings {
    endpoints: Vec<Endpoint>,
    #[serde(default)]
    expected_egress_ip: Option<IpAddr>,
}
impl Settings {
    fn load() -> Check<Self> {
        let json = std::env::var("PRETTYLISA_HEALTH_CONFIG").unwrap_or_else(|_| r#"{"endpoints":[{"url":"https://api.ipify.org/","expected_status":200,"public_ip_body":true},{"url":"https://checkip.amazonaws.com/","expected_status":200,"public_ip_body":true}]}"#.into());
        serde_json::from_str(&json).map_err(|_| "UNKNOWN")
    }
    fn validate(&self) -> Check<()> {
        if self.endpoints.is_empty() || self.endpoints.len() > 4 {
            return Err("UNKNOWN");
        }
        for endpoint in &self.endpoints {
            let url = Url::parse(&endpoint.url).map_err(|_| "UNKNOWN")?;
            if url.scheme() != "https"
                || url.domain().is_none()
                || !url.username().is_empty()
                || url.password().is_some()
                || url.fragment().is_some()
                || endpoint.url.len() > 2048
                || !(200..300).contains(&endpoint.expected_status)
                || endpoint
                    .expected_body
                    .as_ref()
                    .is_some_and(|s| s.len() > 4096)
                || (endpoint.expected_body.is_none() && !endpoint.public_ip_body)
                || (self.expected_egress_ip.is_some() && !endpoint.public_ip_body)
            {
                return Err("UNKNOWN");
            }
        }
        Ok(())
    }
}
trait Probe {
    fn dns(&self, host: &str) -> Check<IpAddr>;
    fn https(&self, url: &Url, ip: IpAddr) -> Check<(u16, Vec<u8>)>;
}
pub fn verify(path: &PathContext) -> Verification {
    match Settings::load() {
        Ok(settings) => verify_with(
            &settings,
            &NetworkProbe {
                path,
                deadline: Instant::now() + Duration::from_secs(15),
            },
        ),
        Err(code) => Verification::failed(true, code),
    }
}
fn verify_with(settings: &Settings, probe: &impl Probe) -> Verification {
    if let Err(code) = settings.validate() {
        return Verification::failed(true, code);
    }
    let mut failure = "HTTPS_CHECK_FAILED";
    for endpoint in &settings.endpoints {
        let check = (|| {
            let url = Url::parse(&endpoint.url).map_err(|_| "UNKNOWN")?;
            let ip = probe.dns(url.domain().ok_or("DNS_FAILED")?)?;
            let (status, body) = probe.https(&url, ip)?;
            if status != endpoint.expected_status
                || endpoint
                    .expected_body
                    .as_ref()
                    .is_some_and(|expected| expected.as_bytes() != body)
            {
                return Err("HTTPS_CHECK_FAILED");
            }
            let egress = if endpoint.public_ip_body {
                let ip: IpAddr = std::str::from_utf8(&body)
                    .map_err(|_| "HTTPS_CHECK_FAILED")?
                    .trim()
                    .parse()
                    .map_err(|_| "HTTPS_CHECK_FAILED")?;
                if !public_ip(ip) {
                    return Err("EGRESS_MISMATCH");
                }
                if settings
                    .expected_egress_ip
                    .is_some_and(|expected| expected != ip)
                {
                    return Err("EGRESS_MISMATCH");
                }
                Some(ip)
            } else {
                None
            };
            Ok(egress)
        })();
        match check {
            Ok(egress) => {
                return Verification {
                    tunnel_established: true,
                    internet_verified: true,
                    failure_code: None,
                    public_egress_ip: egress,
                }
            }
            Err(code @ ("ROUTE_LEAK_DETECTED" | "EGRESS_MISMATCH")) => {
                return Verification::failed(true, code)
            }
            Err(code) => failure = code,
        }
    }
    Verification::failed(true, failure)
}
fn public_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(ip) => {
            !ip.is_private()
                && !ip.is_loopback()
                && !ip.is_link_local()
                && !ip.is_unspecified()
                && !ip.is_multicast()
                && !ip.is_broadcast()
                && !ip.is_documentation()
                && ip.octets()[0] != 0
                && ip.octets()[0] < 240
                && !(ip.octets()[0] == 100 && (64..128).contains(&ip.octets()[1]))
        }
        IpAddr::V6(_) => false, // Current Windows tunnel is IPv4-only.
    }
}
struct NetworkProbe<'a> {
    path: &'a PathContext,
    deadline: Instant,
}
impl NetworkProbe<'_> {
    fn remaining(&self) -> Check<Duration> {
        self.deadline
            .checked_duration_since(Instant::now())
            .filter(|d| !d.is_zero())
            .map(|d| d.min(Duration::from_secs(3)))
            .ok_or("TRANSPORT_TIMEOUT")
    }
    fn socket(&self, target: IpAddr, tcp: bool) -> Check<Socket> {
        let index = crate::wireguard_tunnel::verification_route(target, self.path.luid)?;
        let socket = Socket::new(
            Domain::IPV4,
            if tcp { Type::STREAM } else { Type::DGRAM },
            Some(if tcp { Protocol::TCP } else { Protocol::UDP }),
        )
        .map_err(|_| "UNKNOWN")?;
        pin_interface(&socket, index)?;
        socket
            .bind(&SocketAddr::new(self.path.source, 0).into())
            .map_err(|_| "ROUTE_LEAK_DETECTED")?;
        socket
            .set_read_timeout(Some(self.remaining()?))
            .map_err(|_| "UNKNOWN")?;
        socket
            .set_write_timeout(Some(self.remaining()?))
            .map_err(|_| "UNKNOWN")?;
        Ok(socket)
    }
}
#[cfg(windows)]
fn pin_interface(socket: &Socket, index: u32) -> Check<()> {
    use std::os::windows::io::AsRawSocket;
    use windows_sys::Win32::Networking::WinSock::{setsockopt, IPPROTO_IP, IP_UNICAST_IF};
    let value = index.to_be();
    // IP_UNICAST_IF accepts the interface index in network byte order.
    let result = unsafe {
        setsockopt(
            socket.as_raw_socket() as usize,
            IPPROTO_IP,
            IP_UNICAST_IF,
            (&value as *const u32).cast(),
            4,
        )
    };
    if result != 0 {
        return Err("ROUTE_LEAK_DETECTED");
    }
    Ok(())
}
#[cfg(not(windows))]
fn pin_interface(_: &Socket, _: u32) -> Check<()> {
    Err("ROUTE_LEAK_DETECTED")
}
impl Probe for NetworkProbe<'_> {
    fn dns(&self, host: &str) -> Check<IpAddr> {
        let name = Name::from_ascii(host).map_err(|_| "DNS_FAILED")?;
        let mut query = Message::new();
        let id = rand_core::RngCore::next_u32(&mut rand_core::OsRng) as u16;
        query
            .set_id(id)
            .set_recursion_desired(true)
            .add_query(Query::query(name, RecordType::A));
        let packet = query.to_vec().map_err(|_| "DNS_FAILED")?;
        for server in &self.path.dns {
            let socket = self.socket(*server, false)?;
            let udp: UdpSocket = socket.into();
            udp.connect(SocketAddr::new(*server, 53))
                .map_err(|_| "DNS_FAILED")?;
            if udp.send(&packet).is_err() {
                continue;
            }
            let mut buffer = [0; 4096];
            let received = udp.recv(&mut buffer);
            crate::wireguard_tunnel::verification_route(*server, self.path.luid)?;
            if let Ok(size) = received {
                let response = Message::from_vec(&buffer[..size]).map_err(|_| "DNS_FAILED")?;
                if response.id() != id
                    || response.message_type() != MessageType::Response
                    || response.response_code() != ResponseCode::NoError
                    || response.truncated()
                    || response.queries() != query.queries()
                {
                    continue;
                }
                for answer in response.answers() {
                    if let Some(RData::A(address)) = answer.data() {
                        let ip = IpAddr::V4(address.0);
                        if public_ip(ip) {
                            return Ok(ip);
                        }
                    }
                }
            }
        }
        Err("DNS_FAILED")
    }
    fn https(&self, url: &Url, ip: IpAddr) -> Check<(u16, Vec<u8>)> {
        let socket = self.socket(ip, true)?;
        socket
            .connect_timeout(
                &SocketAddr::new(ip, url.port_or_known_default().ok_or("HTTPS_CHECK_FAILED")?)
                    .into(),
                self.remaining()?,
            )
            .map_err(|error| match error.kind() {
                std::io::ErrorKind::TimedOut | std::io::ErrorKind::WouldBlock => {
                    "TRANSPORT_TIMEOUT"
                }
                _ => "SERVER_UNREACHABLE",
            })?;
        let tcp: TcpStream = socket.into();
        let roots = RootCertStore::from_iter(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());
        let config =
            ClientConfig::builder_with_provider(Arc::new(rustls::crypto::ring::default_provider()))
                .with_safe_default_protocol_versions()
                .map_err(|_| "HTTPS_CHECK_FAILED")?
                .with_root_certificates(roots)
                .with_no_client_auth();
        let host = url.domain().ok_or("HTTPS_CHECK_FAILED")?;
        let name = rustls::pki_types::ServerName::try_from(host.to_owned())
            .map_err(|_| "HTTPS_CHECK_FAILED")?;
        let connection =
            ClientConnection::new(Arc::new(config), name).map_err(|_| "HTTPS_CHECK_FAILED")?;
        let mut tls = StreamOwned::new(
            connection,
            DeadlineStream {
                tcp,
                deadline: self.deadline,
            },
        );
        let path = &url[url::Position::BeforePath..url::Position::AfterQuery];
        let authority = &url[url::Position::BeforeHost..url::Position::AfterPort];
        let request = format!("GET {path} HTTP/1.1\r\nHost: {authority}\r\nConnection: close\r\nCache-Control: no-cache\r\nAccept-Encoding: identity\r\n\r\n");
        tls.write_all(request.as_bytes())
            .map_err(|_| "HTTPS_CHECK_FAILED")?;
        let mut raw = Vec::new();
        let result = Read::by_ref(&mut tls)
            .take((MAX_RESPONSE + 1) as u64)
            .read_to_end(&mut raw);
        crate::wireguard_tunnel::verification_route(ip, self.path.luid)?;
        if raw.len() > MAX_RESPONSE {
            return Err("HTTPS_CHECK_FAILED");
        }
        parse_response(&raw, result.is_ok())
    }
}
// Update the timeout on every operation, including during TLS negotiation.
struct DeadlineStream {
    tcp: TcpStream,
    deadline: Instant,
}
impl DeadlineStream {
    fn timeout(&self) -> std::io::Result<()> {
        let remaining = self
            .deadline
            .checked_duration_since(Instant::now())
            .filter(|d| !d.is_zero())
            .ok_or(std::io::ErrorKind::TimedOut)?;
        self.tcp
            .set_read_timeout(Some(remaining.min(Duration::from_secs(3))))?;
        self.tcp
            .set_write_timeout(Some(remaining.min(Duration::from_secs(3))))
    }
}
impl Read for DeadlineStream {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        self.timeout()?;
        self.tcp.read(buf)
    }
}
impl Write for DeadlineStream {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        self.timeout()?;
        self.tcp.write(buf)
    }
    fn flush(&mut self) -> std::io::Result<()> {
        self.timeout()?;
        self.tcp.flush()
    }
}
fn parse_response(raw: &[u8], clean_eof: bool) -> Check<(u16, Vec<u8>)> {
    let mut headers = [httparse::EMPTY_HEADER; 32];
    let mut response = httparse::Response::new(&mut headers);
    let offset = match response.parse(raw).map_err(|_| "HTTPS_CHECK_FAILED")? {
        httparse::Status::Complete(n) => n,
        _ => return Err("HTTPS_CHECK_FAILED"),
    };
    let status = response.code.ok_or("HTTPS_CHECK_FAILED")?;
    let body = &raw[offset..];
    let lengths: Vec<_> = response
        .headers
        .iter()
        .filter(|h| h.name.eq_ignore_ascii_case("content-length"))
        .collect();
    let encodings: Vec<_> = response
        .headers
        .iter()
        .filter(|h| h.name.eq_ignore_ascii_case("transfer-encoding"))
        .collect();
    if lengths.len() > 1 || encodings.len() > 1 || (!lengths.is_empty() && !encodings.is_empty()) {
        return Err("HTTPS_CHECK_FAILED");
    }
    if let Some(header) = encodings.first() {
        if !header.value.eq_ignore_ascii_case(b"chunked") {
            return Err("HTTPS_CHECK_FAILED");
        }
        let mut remaining = body;
        let mut decoded = Vec::new();
        loop {
            let (offset, size) =
                match httparse::parse_chunk_size(remaining).map_err(|_| "HTTPS_CHECK_FAILED")? {
                    httparse::Status::Complete(value) => value,
                    _ => return Err("HTTPS_CHECK_FAILED"),
                };
            let size = usize::try_from(size).map_err(|_| "HTTPS_CHECK_FAILED")?;
            remaining = &remaining[offset..];
            if size > MAX_RESPONSE
                || remaining.len() < size + 2
                || &remaining[size..size + 2] != b"\r\n"
            {
                return Err("HTTPS_CHECK_FAILED");
            }
            if size == 0 {
                return Ok((status, decoded));
            }
            decoded.extend_from_slice(&remaining[..size]);
            remaining = &remaining[size + 2..];
        }
    }
    if let Some(header) = lengths.first() {
        let length: usize = std::str::from_utf8(header.value)
            .map_err(|_| "HTTPS_CHECK_FAILED")?
            .parse()
            .map_err(|_| "HTTPS_CHECK_FAILED")?;
        if length != body.len() {
            return Err("HTTPS_CHECK_FAILED");
        }
    } else if !clean_eof {
        return Err("HTTPS_CHECK_FAILED");
    }
    Ok((status, body.to_vec()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    struct Fake {
        dns: Check<IpAddr>,
        response: Check<(u16, Vec<u8>)>,
        calls: Cell<usize>,
    }
    impl Probe for Fake {
        fn dns(&self, _: &str) -> Check<IpAddr> {
            self.dns
        }
        fn https(&self, _: &Url, _: IpAddr) -> Check<(u16, Vec<u8>)> {
            self.calls.set(self.calls.get() + 1);
            self.response.clone()
        }
    }
    fn settings() -> Settings {
        serde_json::from_str(r#"{"endpoints":[{"url":"https://health.example.test/check","expected_status":200,"expected_body":"ok"}]}"#).unwrap()
    }
    fn fake() -> Fake {
        Fake {
            dns: Ok("1.1.1.1".parse().unwrap()),
            response: Ok((200, b"ok".to_vec())),
            calls: Cell::new(0),
        }
    }
    #[test]
    fn tunnel_up_without_internet_is_not_verified() {
        for code in [
            "DNS_FAILED",
            "HTTPS_CHECK_FAILED",
            "TRANSPORT_TIMEOUT",
            "ROUTE_LEAK_DETECTED",
        ] {
            let mut probe = fake();
            if code == "DNS_FAILED" {
                probe.dns = Err(code);
            } else {
                probe.response = Err(code);
            }
            let result = verify_with(&settings(), &probe);
            assert!(result.tunnel_established);
            assert!(!result.internet_verified);
            assert_eq!(result.failure_code, Some(code));
        }
    }
    #[test]
    fn requires_expected_status_and_body() {
        assert!(verify_with(&settings(), &fake()).internet_verified);
        for response in [
            (302, b"ok".to_vec()),
            (200, b"portal".to_vec()),
            (500, b"ok".to_vec()),
        ] {
            let mut probe = fake();
            probe.response = Ok(response);
            assert_eq!(
                verify_with(&settings(), &probe).failure_code,
                Some("HTTPS_CHECK_FAILED")
            );
        }
    }
    #[test]
    fn checks_egress_and_does_not_mask_leaks_with_another_endpoint() {
        let mut settings = settings();
        settings.endpoints.push(Endpoint {
            url: "https://other.example.test/".into(),
            expected_status: 200,
            expected_body: Some("ok".into()),
            public_ip_body: false,
        });
        let mut probe = fake();
        probe.response = Err("ROUTE_LEAK_DETECTED");
        assert_eq!(
            verify_with(&settings, &probe).failure_code,
            Some("ROUTE_LEAK_DETECTED")
        );
        assert_eq!(probe.calls.get(), 1);
        settings.endpoints.truncate(1);
        settings.endpoints[0].expected_body = None;
        settings.endpoints[0].public_ip_body = true;
        settings.expected_egress_ip = Some("1.1.1.1".parse().unwrap());
        probe.response = Ok((200, b"8.8.8.8\n".to_vec()));
        assert_eq!(
            verify_with(&settings, &probe).failure_code,
            Some("EGRESS_MISMATCH")
        );
        probe.response = Ok((200, b"1.1.1.1\n".to_vec()));
        assert_eq!(
            verify_with(&settings, &probe).public_egress_ip,
            settings.expected_egress_ip
        );
    }
    #[test]
    fn supports_multiple_endpoints_without_transport_fallback() {
        struct Multiple(Cell<usize>);
        impl Probe for Multiple {
            fn dns(&self, _: &str) -> Check<IpAddr> {
                Ok("1.1.1.1".parse().unwrap())
            }
            fn https(&self, _: &Url, _: IpAddr) -> Check<(u16, Vec<u8>)> {
                self.0.set(self.0.get() + 1);
                if self.0.get() == 1 {
                    Err("HTTPS_CHECK_FAILED")
                } else {
                    Ok((200, b"ok".to_vec()))
                }
            }
        }
        let mut config = settings();
        config.endpoints.push(settings().endpoints.remove(0));
        let probe = Multiple(Cell::new(0));
        assert!(verify_with(&config, &probe).internet_verified);
        assert_eq!(probe.0.get(), 2);
    }
    #[test]
    fn rejects_insecure_or_ambiguous_config() {
        for url in [
            "http://health.example.test/",
            "https://user:secret@health.example.test/",
            "https://1.1.1.1/",
            "https://health.example.test/#fragment",
        ] {
            let mut config = settings();
            config.endpoints[0].url = url.into();
            assert!(config.validate().is_err());
        }
        let mut config = settings();
        config.endpoints.clear();
        assert!(config.validate().is_err());
    }
    #[test]
    fn parses_bounded_complete_http_responses_only() {
        assert_eq!(
            parse_response(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok", false).unwrap(),
            (200, b"ok".to_vec())
        );
        assert_eq!(
            parse_response(
                b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\nok\r\n0\r\n\r\n",
                false
            )
            .unwrap(),
            (200, b"ok".to_vec())
        );
        for raw in [
            b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nok".as_slice(),
            b"HTTP/1.1 200 OK\r\n\r\nok",
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\nok",
            b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nTransfer-Encoding: chunked\r\n\r\nok",
        ] {
            assert!(parse_response(raw, false).is_err());
        }
    }
    #[test]
    fn rejects_physical_route_before_sending_probe_traffic() {
        // No actual network request: the impossible LUID cannot match any route.
        let path = PathContext {
            luid: u64::MAX,
            source: "127.0.0.1".parse().unwrap(),
            dns: vec!["1.1.1.1".parse().unwrap()],
        };
        let probe = NetworkProbe {
            path: &path,
            deadline: Instant::now() + Duration::from_secs(1),
        };
        assert_eq!(probe.dns("health.example.test"), Err("ROUTE_LEAK_DETECTED"));
    }
}
