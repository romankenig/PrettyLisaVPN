//! Managed upstream v1.6 sidecar. No WireGuard private key crosses this boundary.
use std::net::{Ipv4Addr, SocketAddr, UdpSocket};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use crate::debug_log;
use crate::obfuscation_transport::TransportError;

pub(crate) struct Client {
    pub(crate) local_endpoint: SocketAddr,
    pub(crate) public_endpoint: SocketAddr,
    child: Mutex<Child>,
    #[cfg(windows)]
    _job: Job,
}

fn settings<'a>(port: Option<&str>, masking: &'a str) -> Result<(u16, &'a str), TransportError> {
    let port = port
        .unwrap_or("443")
        .parse::<u16>()
        .map_err(|_| TransportError::InvalidConfiguration)?;
    if port == 0 || !matches!(masking, "NONE" | "STUN") {
        return Err(TransportError::InvalidConfiguration);
    }
    Ok((port, masking))
}

// Restrict the upstream config to one key assignment. In particular it cannot enable
// TRACE, additional instances, allow-clean, target overrides or shell-like input.
fn validate_key_file(value: &str) -> bool {
    let Some(key) = value.trim().strip_prefix("key=") else {
        return false;
    };
    key.len() == 64 && key.bytes().all(|byte| byte.is_ascii_hexdigit())
}

impl Client {
    pub(crate) fn start(endpoint: SocketAddr) -> Result<Self, TransportError> {
        let port = std::env::var("PRETTYLISA_WG_OBFUSCATOR_PORT").ok();
        let masking =
            std::env::var("PRETTYLISA_WG_OBFUSCATOR_MASKING").unwrap_or_else(|_| "NONE".into());
        let (port, masking) = settings(port.as_deref(), &masking)?;
        if !endpoint.is_ipv4() || endpoint.ip().is_unspecified() {
            return Err(TransportError::InvalidConfiguration);
        }
        let executable = PathBuf::from(
            std::env::var_os("PRETTYLISA_WG_OBFUSCATOR_EXE")
                .ok_or(TransportError::InvalidConfiguration)?,
        );
        let config = PathBuf::from(
            std::env::var_os("PRETTYLISA_WG_OBFUSCATOR_KEY_FILE")
                .ok_or(TransportError::InvalidConfiguration)?,
        );
        if !executable.is_absolute() || !config.is_absolute() {
            return Err(TransportError::InvalidConfiguration);
        }
        verify_components(&executable)?;
        let contents = zeroize::Zeroizing::new(
            std::fs::read_to_string(&config).map_err(|_| TransportError::InvalidConfiguration)?,
        );
        if !validate_key_file(&contents) {
            return Err(TransportError::InvalidConfiguration);
        }
        let reservation =
            UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).map_err(|_| TransportError::Unavailable)?;
        let local_endpoint = reservation
            .local_addr()
            .map_err(|_| TransportError::Unavailable)?;
        let public_endpoint = SocketAddr::new(endpoint.ip(), port);
        let mut command = Command::new(executable);
        command
            .arg("--config")
            .arg(config)
            .args([
                "--source-if",
                "127.0.0.1",
                "--source-lport",
                &local_endpoint.port().to_string(),
                "--target",
                &public_endpoint.to_string(),
                "--masking",
                masking,
                "--verbose",
                "0",
                "--max-clients",
                "1",
            ])
            // Do not pass unrelated application credentials to the sidecar.
            .env_clear()
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        if let Some(root) = std::env::var_os("SystemRoot") {
            command.env("SystemRoot", root);
        }
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000004); // CREATE_NO_WINDOW | CREATE_SUSPENDED
        }
        // Upstream cannot inherit our bound socket. Confirm socket ownership after spawn,
        // so a port-allocation race fails closed instead of configuring WireGuard to a stranger.
        drop(reservation);
        let mut child = command.spawn().map_err(|_| TransportError::Unavailable)?;
        debug_log::event("wg_obfuscator_spawned", format_args!("pid={}", child.id()));
        #[cfg(windows)]
        let job = match Job::attach(&child) {
            Ok(job) => job,
            Err(error) => {
                debug_log::event(
                    "wg_obfuscator_job_failed",
                    format_args!(
                        "os_error={:?}",
                        std::io::Error::last_os_error().raw_os_error()
                    ),
                );
                let _ = child.kill();
                let _ = child.wait();
                return Err(error);
            }
        };
        #[cfg(windows)]
        if !resume_child(child.id()) {
            debug_log::event(
                "wg_obfuscator_resume_failed",
                format_args!("pid={}", child.id()),
            );
            let _ = child.kill();
            let _ = child.wait();
            return Err(TransportError::Unavailable);
        }
        let client = Self {
            local_endpoint,
            public_endpoint,
            child: Mutex::new(child),
            #[cfg(windows)]
            _job: job,
        };
        let deadline = Instant::now() + Duration::from_secs(3);
        while Instant::now() < deadline {
            if !client.is_healthy() {
                debug_log::event(
                    "wg_obfuscator_early_exit",
                    format_args!(
                        "status={:?}",
                        client
                            .child
                            .lock()
                            .ok()
                            .and_then(|mut c| c.try_wait().ok())
                            .flatten()
                    ),
                );
                return Err(TransportError::Unavailable);
            }
            if client.listener_ready() {
                debug_log::event("wg_obfuscator_ready", format_args!("version=1.6 masking={masking} local_endpoint={local_endpoint} public_endpoint={public_endpoint} counters_available=false"));
                return Ok(client);
            }
            std::thread::sleep(Duration::from_millis(25));
        }
        Err(TransportError::Unavailable)
    }

    pub(crate) fn is_healthy(&self) -> bool {
        self.child
            .lock()
            .is_ok_and(|mut child| matches!(child.try_wait(), Ok(None)))
    }

    fn listener_ready(&self) -> bool {
        #[cfg(windows)]
        if let Ok(child) = self.child.lock() {
            return owns_udp_listener(child.id(), self.local_endpoint.port());
        }
        false
    }

    pub(crate) fn stop(&self) {
        if let Ok(mut child) = self.child.lock() {
            if matches!(child.try_wait(), Ok(None)) {
                let _ = child.kill();
            }
            let _ = child.wait();
        }
    }
}

impl Drop for Client {
    fn drop(&mut self) {
        self.stop();
    }
}

fn verify_components(executable: &std::path::Path) -> Result<(), TransportError> {
    use sha2::{Digest, Sha256};
    let root = executable
        .parent()
        .ok_or(TransportError::InvalidConfiguration)?;
    for (path, expected) in [
        (
            executable.to_path_buf(),
            "9bc2f528c2ee612548831305f8f09c83f63004ae95c164995686b4de7c60a68f",
        ),
        (
            root.join("msys-2.0.dll"),
            "e0223cfad346a02ccb78c35b0f5a8036057304a3d8d2458881775d8674a5ac14",
        ),
        (
            root.join("msys-gcc_s-seh-1.dll"),
            "59b816ee2880c2140ac8d7726f59e4e7435e309f272a80fd590d3130215f77f5",
        ),
    ] {
        let bytes = std::fs::read(path).map_err(|_| TransportError::Unavailable)?;
        if format!("{:x}", Sha256::digest(bytes)) != expected {
            return Err(TransportError::InvalidConfiguration);
        }
    }
    Ok(())
}

#[cfg(windows)]
fn resume_child(pid: u32) -> bool {
    use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::System::{Diagnostics::ToolHelp::*, Threading::*};
    unsafe {
        let snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
        if snapshot == INVALID_HANDLE_VALUE {
            return false;
        }
        let mut entry: THREADENTRY32 = std::mem::zeroed();
        entry.dwSize = std::mem::size_of_val(&entry) as u32;
        let mut found = Thread32First(snapshot, &mut entry);
        let mut resumed = false;
        while found != 0 {
            if entry.th32OwnerProcessID == pid {
                let thread = OpenThread(THREAD_SUSPEND_RESUME, 0, entry.th32ThreadID);
                if !thread.is_null() {
                    resumed = ResumeThread(thread) != u32::MAX;
                    CloseHandle(thread);
                }
                break;
            }
            found = Thread32Next(snapshot, &mut entry);
        }
        CloseHandle(snapshot);
        resumed
    }
}

#[cfg(windows)]
struct Job(windows_sys::Win32::Foundation::HANDLE);
// Owned kernel handle; access does not mutate Rust memory. Close only at Drop.
#[cfg(windows)]
unsafe impl Send for Job {}
#[cfg(windows)]
unsafe impl Sync for Job {}

#[cfg(windows)]
impl Job {
    fn attach(child: &Child) -> Result<Self, TransportError> {
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::System::JobObjects::*;
        unsafe {
            let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if handle.is_null() {
                return Err(TransportError::Unavailable);
            }
            let job = Self(handle);
            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                &limits as *const _ as _,
                std::mem::size_of_val(&limits) as u32,
            ) == 0
                || AssignProcessToJobObject(handle, child.as_raw_handle()) == 0
            {
                return Err(TransportError::Unavailable);
            }
            Ok(job)
        }
    }
}

#[cfg(windows)]
impl Drop for Job {
    fn drop(&mut self) {
        unsafe {
            windows_sys::Win32::Foundation::CloseHandle(self.0);
        }
    }
}

#[cfg(windows)]
fn owns_udp_listener(pid: u32, port: u16) -> bool {
    use windows_sys::Win32::NetworkManagement::IpHelper::*;
    // Aligned storage and a bounded retry: table size can change while other apps bind UDP.
    for _ in 0..3 {
        let mut size = 0;
        unsafe {
            GetExtendedUdpTable(
                std::ptr::null_mut(),
                &mut size,
                0,
                2,
                UDP_TABLE_OWNER_PID,
                0,
            );
        }
        if !(4..=16 * 1024 * 1024).contains(&size) {
            return false;
        }
        let mut storage = vec![0_u32; (size as usize).div_ceil(4)];
        let result = unsafe {
            GetExtendedUdpTable(
                storage.as_mut_ptr().cast(),
                &mut size,
                0,
                2,
                UDP_TABLE_OWNER_PID,
                0,
            )
        };
        if result != 0 {
            continue;
        }
        let count = storage[0] as usize;
        let row_size = std::mem::size_of::<MIB_UDPROW_OWNER_PID>();
        if 4 + count * row_size > storage.len() * 4 {
            return false;
        }
        for index in 0..count {
            let row = unsafe {
                std::ptr::read_unaligned(
                    storage
                        .as_ptr()
                        .cast::<u8>()
                        .add(4 + index * row_size)
                        .cast::<MIB_UDPROW_OWNER_PID>(),
                )
            };
            if row.dwOwningPid == pid
                && u16::from_be(row.dwLocalPort as u16) == port
                && Ipv4Addr::from(row.dwLocalAddr.to_ne_bytes()) == Ipv4Addr::LOCALHOST
            {
                return true;
            }
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;
    // Run alone with the pinned installed executable; never reads the production key.
    #[cfg(windows)]
    #[test]
    #[ignore = "requires pinned upstream v1.6 executable (PRETTYLISA_WG_OBFUSCATOR_EXE)"]
    fn upstream_roundtrip_lifecycle_and_failure_cleanup() {
        let exe = std::env::var_os("PRETTYLISA_WG_OBFUSCATOR_EXE").expect("install pinned release");
        let key_path =
            std::env::temp_dir().join(format!("plvpn-test-{}.conf", uuid::Uuid::new_v4()));
        std::fs::write(&key_path, format!("key={}\n", "a".repeat(64))).unwrap();
        std::env::set_var("PRETTYLISA_WG_OBFUSCATOR_KEY_FILE", &key_path);
        for masking in ["NONE", "STUN"] {
            let wg = UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
            wg.set_read_timeout(Some(Duration::from_secs(2))).unwrap();
            let reservation = UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
            let port = reservation.local_addr().unwrap().port();
            drop(reservation);
            let mut command = Command::new(&exe);
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
            let mut server = command
                .arg("--config")
                .arg(&key_path)
                .args([
                    "--source-if",
                    "127.0.0.1",
                    "--source-lport",
                    &port.to_string(),
                    "--target",
                    &wg.local_addr().unwrap().to_string(),
                    "--masking",
                    masking,
                    "--verbose",
                    "0",
                ])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .unwrap();
            let job = Job::attach(&server).unwrap();
            let deadline = Instant::now() + Duration::from_secs(3);
            while !owns_udp_listener(server.id(), port) && Instant::now() < deadline {
                std::thread::sleep(Duration::from_millis(25));
            }
            assert!(
                owns_udp_listener(server.id(), port),
                "server exit={:?}",
                server.try_wait()
            );
            std::env::set_var("PRETTYLISA_WG_OBFUSCATOR_PORT", port.to_string());
            std::env::set_var("PRETTYLISA_WG_OBFUSCATOR_MASKING", masking);
            let client = Client::start("127.0.0.1:51820".parse().unwrap()).unwrap();
            let local = client.local_endpoint;
            let peer = UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
            peer.set_read_timeout(Some(Duration::from_secs(2))).unwrap();
            let mut handshake = [0_u8; 148];
            handshake[0] = 1;
            peer.send_to(&handshake, local).unwrap();
            let mut buffer = [0_u8; 4096];
            let (size, source) = wg.recv_from(&mut buffer).unwrap();
            assert_eq!(&buffer[..size], handshake);
            let mut reply = [0_u8; 92];
            reply[0] = 2;
            wg.send_to(&reply, source).unwrap();
            let (size, _) = peer.recv_from(&mut buffer).unwrap();
            assert_eq!(&buffer[..size], reply);
            assert!(client.is_healthy());
            client.stop();
            client.stop();
            assert!(!client.is_healthy());
            assert!(UdpSocket::bind(local).is_ok());
            let failed_connection = Client::start("127.0.0.1:51820".parse().unwrap()).unwrap();
            let released = failed_connection.local_endpoint;
            drop(failed_connection);
            assert!(UdpSocket::bind(released).is_ok());
            // The server has already loaded 'a'; an incompatible obfuscation key must
            // not deliver this synthetic handshake to the local WireGuard socket.
            std::fs::write(&key_path, format!("key={}\n", "b".repeat(64))).unwrap();
            let wrong_key = Client::start("127.0.0.1:51820".parse().unwrap()).unwrap();
            peer.send_to(&handshake, wrong_key.local_endpoint).unwrap();
            assert!(wg.recv_from(&mut buffer).is_err());
            drop(wrong_key);
            std::fs::write(&key_path, format!("key={}\n", "a".repeat(64))).unwrap();
            let crashed = Client::start("127.0.0.1:51820".parse().unwrap()).unwrap();
            crashed.child.lock().unwrap().kill().unwrap();
            crashed.child.lock().unwrap().wait().unwrap();
            assert!(!crashed.is_healthy());
            drop(crashed);
            drop(job); // verifies job-close kills the upstream server
            server.wait().unwrap();
            assert!(UdpSocket::bind((Ipv4Addr::LOCALHOST, port)).is_ok());
        }
        std::fs::remove_file(key_path).unwrap();
    }
    #[test]
    fn missing_component_is_rejected() {
        let missing = std::env::temp_dir()
            .join(uuid::Uuid::new_v4().to_string())
            .join("wg-obfuscator.exe");
        assert!(verify_components(&missing).is_err());
    }
    #[test]
    fn rejects_config_injection_and_short_keys() {
        assert!(validate_key_file(&format!("key={}\n", "a".repeat(64))));
        for invalid in [
            "key=test",
            "key=abc\nverbose=TRACE",
            "[main]\nkey=test",
            "key=$(whoami)",
        ] {
            assert!(!validate_key_file(invalid));
        }
    }
    #[test]
    fn explicit_masking_and_valid_port_only() {
        assert_eq!(settings(None, "NONE").unwrap(), (443, "NONE"));
        assert_eq!(settings(Some("8443"), "STUN").unwrap(), (8443, "STUN"));
        for mode in ["AUTO", "STUN;cmd", ""] {
            assert!(settings(None, mode).is_err());
        }
        for port in ["0", "65536", "443\n"] {
            assert!(settings(Some(port), "NONE").is_err());
        }
    }
    #[cfg(windows)]
    #[test]
    fn listener_readiness_checks_owner_and_address() {
        let socket = UdpSocket::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let port = socket.local_addr().unwrap().port();
        assert!(owns_udp_listener(std::process::id(), port));
        assert!(!owns_udp_listener(u32::MAX, port));
        drop(socket);
        assert!(!owns_udp_listener(std::process::id(), port));
    }
}
