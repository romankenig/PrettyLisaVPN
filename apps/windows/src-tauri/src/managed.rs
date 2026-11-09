//! The installed Windows service owns the engine; the GUI stays unelevated.
//! Local authenticated pipe, bounded typed profiles, no secrets in argv.
use serde_json::{json, Value};
use std::{
    ffi::OsStr,
    fs::{self, File, OpenOptions},
    io::{BufRead, BufReader, Read, Write},
    os::windows::{
        ffi::OsStrExt,
        fs::OpenOptionsExt,
        io::{AsRawHandle, FromRawHandle},
        process::CommandExt,
    },
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{mpsc, Mutex},
    time::{Duration, Instant},
};
use tauri::{AppHandle, Manager};
use windows_sys::Win32::{
    Foundation::*,
    Security::{
        Authorization::ConvertStringSecurityDescriptorToSecurityDescriptorW, SECURITY_ATTRIBUTES,
    },
    Storage::FileSystem::*,
    System::{JobObjects::*, Pipes::*, SystemInformation::GetSystemDirectoryW, Threading::*},
};
use zeroize::Zeroizing;

const ERROR: &str = "ENGINE_UNAVAILABLE";
const FRAME_LIMIT: usize = 132_096;
const NO_WINDOW: u32 = 0x08000000;
const EMBEDDED_ENGINE: &[u8] = include_bytes!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/engine/pl-engine.exe.gz"
));

fn unpack_engine(content: &[u8]) -> Result<Vec<u8>, &'static str> {
    const LIMIT: u64 = 64 * 1024 * 1024;
    let mut decoded = Vec::new();
    flate2::read::GzDecoder::new(content)
        .take(LIMIT + 1)
        .read_to_end(&mut decoded)
        .map_err(|_| ERROR)?;
    if decoded.len() < 64 || decoded.len() as u64 > LIMIT || !decoded.starts_with(b"MZ") {
        return Err(ERROR);
    }
    Ok(decoded)
}

struct Handle(HANDLE);
unsafe impl Send for Handle {}
impl Drop for Handle {
    fn drop(&mut self) {
        unsafe {
            CloseHandle(self.0);
        }
    }
}
struct Session {
    pipe: File,
}
#[derive(Default)]
pub struct ManagedState(Mutex<Connection>);
#[derive(Default)]
struct Connection {
    session: Option<Session>,
    cleanup_pending: bool,
}

fn wide(value: impl AsRef<OsStr>) -> Vec<u16> {
    value.as_ref().encode_wide().chain(Some(0)).collect()
}
fn system_directory() -> Result<PathBuf, &'static str> {
    let mut buffer = vec![0u16; 32768];
    let n = unsafe { GetSystemDirectoryW(buffer.as_mut_ptr(), buffer.len() as u32) } as usize;
    if n == 0 || n >= buffer.len() {
        return Err(ERROR);
    }
    Ok(PathBuf::from(
        String::from_utf16(&buffer[..n]).map_err(|_| ERROR)?,
    ))
}
fn with_acl<T>(
    sddl: &str,
    action: impl FnOnce(*const SECURITY_ATTRIBUTES) -> Result<T, &'static str>,
) -> Result<T, &'static str> {
    unsafe {
        let mut descriptor = std::ptr::null_mut();
        if ConvertStringSecurityDescriptorToSecurityDescriptorW(
            wide(sddl).as_ptr(),
            1,
            &mut descriptor,
            std::ptr::null_mut(),
        ) == 0
        {
            return Err(ERROR);
        }
        let attributes = SECURITY_ATTRIBUTES {
            nLength: std::mem::size_of::<SECURITY_ATTRIBUTES>() as u32,
            lpSecurityDescriptor: descriptor,
            bInheritHandle: 0,
        };
        let result = action(&attributes);
        LocalFree(descriptor);
        result
    }
}
fn pipe_server(name: &str) -> Result<File, &'static str> {
    // Interactive users may exchange data, but cannot create pipe instances.
    with_acl(
        "D:P(D;;GA;;;NU)(A;;GA;;;SY)(A;;GA;;;BA)(A;;0x12019b;;;IU)",
        |acl| unsafe {
            let pipe = CreateNamedPipeW(
                wide(name).as_ptr(),
                PIPE_ACCESS_DUPLEX | FILE_FLAG_FIRST_PIPE_INSTANCE,
                PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_NOWAIT | PIPE_REJECT_REMOTE_CLIENTS,
                1,
                FRAME_LIMIT as u32,
                FRAME_LIMIT as u32,
                0,
                acl,
            );
            if pipe == INVALID_HANDLE_VALUE {
                return Err(ERROR);
            }
            Ok(File::from_raw_handle(pipe))
        },
    )
}
fn pipe_client(name: &str) -> Result<File, &'static str> {
    OpenOptions::new()
        .access_mode(0x120183)
        // Never let a pipe impostor impersonate our interactive user.
        .custom_flags(SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION)
        .open(name)
        .map_err(|_| super::vpn_service::ERROR)
}
fn running(process: &Handle) -> bool {
    unsafe { WaitForSingleObject(process.0, 0) == WAIT_TIMEOUT }
}
fn frame(
    pipe: &mut File,
    process: Option<&Handle>,
    timeout: Duration,
) -> Result<Zeroizing<Vec<u8>>, &'static str> {
    let until = Instant::now() + timeout;
    let mut data = Zeroizing::new(Vec::new());
    while Instant::now() < until {
        let mut byte = [0u8];
        let mut received = 0;
        // File::read normalizes ERROR_NO_DATA to EOF on Windows. For a live
        // PIPE_NOWAIT peer it means "not yet", so retain the Win32 error here.
        let ok = unsafe {
            ReadFile(
                pipe.as_raw_handle(),
                byte.as_mut_ptr(),
                1,
                &mut received,
                std::ptr::null_mut(),
            )
        };
        match (ok, received) {
            (_, 1) if ok != 0 && byte[0] == b'\n' => return Ok(data),
            (_, 1) if ok != 0 => {
                data.push(byte[0]);
                if data.len() > FRAME_LIMIT {
                    return Err("ENGINE_INVALID_RESPONSE");
                }
            }
            (0, _) if unsafe { GetLastError() } == ERROR_NO_DATA => {
                if super::vpn_service::stopping() || process.is_some_and(|p| !running(p)) {
                    return Err(ERROR);
                }
                std::thread::sleep(Duration::from_millis(10));
            }
            _ => return Err(ERROR),
        }
    }
    // Never drop half a command and interpret its suffix as the next frame.
    Err(if data.is_empty() {
        "ENGINE_TIMEOUT"
    } else {
        "ENGINE_INVALID_RESPONSE"
    })
}
fn write_frame(pipe: &mut impl Write, value: &Value) -> Result<(), &'static str> {
    let mut bytes = Zeroizing::new(serde_json::to_vec(value).map_err(|_| ERROR)?);
    if bytes.len() > FRAME_LIMIT {
        return Err("ENGINE_INVALID_CONFIGURATION");
    }
    bytes.push(b'\n');
    pipe.write_all(&bytes)
        .and_then(|_| pipe.flush())
        .map_err(|_| ERROR)
}
fn exchange(session: &mut Session, request: Value) -> Result<Value, &'static str> {
    write_frame(&mut session.pipe, &request)?;
    let bytes = frame(&mut session.pipe, None, Duration::from_secs(40))?;
    serde_json::from_slice(&bytes).map_err(|_| "ENGINE_INVALID_RESPONSE")
}
fn launch() -> Result<Session, &'static str> {
    let expected = super::vpn_service::process_id()?.ok_or(super::vpn_service::ERROR)?;
    let pipe = pipe_client(super::vpn_service::PIPE)?;
    unsafe {
        let mut pid = 0;
        if GetNamedPipeServerProcessId(pipe.as_raw_handle(), &mut pid) == 0 || pid != expected {
            return Err("ENGINE_OWNER_MISMATCH");
        }
        let mode = PIPE_READMODE_BYTE | PIPE_NOWAIT;
        if SetNamedPipeHandleState(
            pipe.as_raw_handle(),
            &mode,
            std::ptr::null(),
            std::ptr::null(),
        ) == 0
        {
            return Err(ERROR);
        }
    }
    Ok(Session { pipe })
}
fn recover(connection: &mut Connection) -> Result<(), &'static str> {
    // The service accepts its next client only after closing the previous job.
    // A disconnected pipe alone is NOT evidence of successful cleanup.
    let until = Instant::now() + Duration::from_secs(10);
    while Instant::now() < until {
        if super::vpn_service::process_id()?.is_none() {
            connection.cleanup_pending = false;
            return Ok(());
        }
        if let Ok(mut session) = launch() {
            if exchange(&mut session, json!({"action":"status"}))?["status"] == "DOWN" {
                connection.session = Some(session);
                connection.cleanup_pending = false;
                return Ok(());
            }
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    Err("ENGINE_CLEANUP_FAILED")
}
fn stop(state: &ManagedState) -> Result<(), &'static str> {
    let mut guard = state.0.lock().map_err(|_| ERROR)?;
    if let Some(mut session) = guard.session.take() {
        if matches!(exchange(&mut session, json!({"action":"stop"})), Ok(value) if value["status"] == "DOWN")
        {
            guard.session = Some(session);
            super::vpn_handoff::flush_dns()?;
            return Ok(());
        }
        guard.cleanup_pending = true;
        drop(session);
    }
    if guard.cleanup_pending {
        recover(&mut guard)?;
    }
    Ok(())
}
/// Read-only installed-client diagnostic used by installer acceptance tests.
/// The caller cannot supply a command, path or profile via this entry point.
pub fn service_check() -> Result<(), &'static str> {
    let result = exchange(&mut launch()?, json!({"action":"status"}))?;
    if result["status"] == "DOWN" {
        Ok(())
    } else {
        Err("ENGINE_CLEANUP_REQUIRED")
    }
}

#[tauri::command]
pub async fn engine_start(app: AppHandle, profile: Value) -> Result<(), &'static str> {
    tauri::async_runtime::spawn_blocking(move || {
        super::wireguard::route_preflight()?;
        let state = app.state::<ManagedState>();
        let mut guard = state.0.lock().map_err(|_| ERROR)?;
        if guard.cleanup_pending {
            recover(&mut guard)?;
        }
        if let Some(session) = guard.session.as_mut() {
            if exchange(session, json!({"action":"status"}))?["status"] != "DOWN" {
                return Err("ENGINE_CLEANUP_REQUIRED");
            }
        } else {
            guard.session = Some(launch()?);
        }
        super::vpn_handoff::flush_dns()?;
        let result = exchange(
            guard.session.as_mut().ok_or(ERROR)?,
            json!({"action":"start","profile":profile}),
        )?;
        if result["status"] != "RUNNING" {
            return Err("ENGINE_START_FAILED");
        }
        Ok(())
    })
    .await
    .map_err(|_| ERROR)?
}
#[tauri::command]
pub async fn engine_stop(app: AppHandle) -> Result<(), &'static str> {
    tauri::async_runtime::spawn_blocking(move || stop(&app.state::<ManagedState>()))
        .await
        .map_err(|_| ERROR)?
}
#[tauri::command]
pub async fn engine_is_up(app: AppHandle) -> Result<bool, &'static str> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<ManagedState>();
        let mut guard = state.0.lock().map_err(|_| ERROR)?;
        let Some(session) = guard.session.as_mut() else {
            return Ok(false);
        };
        Ok(exchange(session, json!({"action":"status"}))?["status"] == "RUNNING")
    })
    .await
    .map_err(|_| ERROR)?
}

pub async fn direct_location(app: AppHandle) -> Result<Value, &'static str> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<ManagedState>();
        let mut guard = state.0.lock().map_err(|_| ERROR)?;
        let session = guard.session.as_mut().ok_or(ERROR)?;
        let result = exchange(session, json!({"action":"direct_location"}))?;
        if result["status"] != "OK" {
            return Err("PUBLIC_LOCATION_UNAVAILABLE");
        }
        Ok(result["location"].clone())
    })
    .await
    .map_err(|_| ERROR)?
}

#[tauri::command]
pub async fn engine_verify(
    app: AppHandle,
    session_id: String,
    access_token: String,
) -> Result<bool, &'static str> {
    if !engine_is_up(app).await? {
        return Err(ERROR);
    }
    let identifier = uuid::Uuid::parse_str(&session_id).map_err(|_| ERROR)?;
    super::wireguard::verify_tunnel(
        std::net::Ipv4Addr::new(172, 30, 255, 1),
        identifier,
        access_token,
        true,
    )
    .await
}

pub fn serve_service(ready: impl FnOnce()) -> Result<(), &'static str> {
    let mut pipe = pipe_server(super::vpn_service::PIPE)?;
    ready();
    while !super::vpn_service::stopping() {
        let connected = unsafe {
            ConnectNamedPipe(pipe.as_raw_handle(), std::ptr::null_mut()) != 0
                || GetLastError() == ERROR_PIPE_CONNECTED
        };
        if !connected {
            std::thread::sleep(Duration::from_millis(20));
            continue;
        }
        if let Ok(parent) = authenticated_parent(&pipe) {
            let _ = serve_owner(&mut pipe, &parent);
        }
        // Keep the first-instance handle to prevent namespace takeover between clients.
        unsafe {
            DisconnectNamedPipe(pipe.as_raw_handle());
        }
    }
    Ok(())
}
fn authenticated_parent(pipe: &File) -> Result<Handle, &'static str> {
    unsafe {
        let mut pid = 0;
        if GetNamedPipeClientProcessId(pipe.as_raw_handle(), &mut pid) == 0 {
            return Err(ERROR);
        }
        let parent = Handle(OpenProcess(
            SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
            0,
            pid,
        ));
        if parent.0.is_null() {
            return Err(ERROR);
        }
        let mut path = vec![0u16; 32768];
        let mut length = path.len() as u32;
        if QueryFullProcessImageNameW(parent.0, 0, path.as_mut_ptr(), &mut length) == 0 {
            return Err(ERROR);
        }
        let path = PathBuf::from(String::from_utf16(&path[..length as usize]).map_err(|_| ERROR)?);
        if fs::canonicalize(path).map_err(|_| ERROR)?
            != fs::canonicalize(super::vpn_service::installed_executable()?).map_err(|_| ERROR)?
        {
            return Err("ENGINE_OWNER_MISMATCH");
        }
        Ok(parent)
    }
}
fn serve_owner(pipe: &mut File, parent: &Handle) -> Result<(), &'static str> {
    // System32 is administrator-owned; a random new directory with a protected
    // DACL prevents DLL/executable replacement or junction planting by other users.
    let directory = system_directory()?.join(format!("PrettyLisaVPN-{}", uuid::Uuid::new_v4()));
    with_acl("D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)", |acl| {
        if unsafe { CreateDirectoryW(wide(&directory).as_ptr(), acl) } == 0 {
            return Err(ERROR);
        }
        Ok(())
    })?;
    let result = serve(pipe, parent, &directory);
    // Exact files in the directory created above; never recursive path deletion.
    for name in ["pl-engine.exe", "wintun.dll"] {
        let _ = fs::remove_file(directory.join(name));
    }
    let _ = fs::remove_dir(directory);
    result
}
fn serve(
    pipe: &mut File,
    parent: &Handle,
    directory: &std::path::Path,
) -> Result<(), &'static str> {
    fs::write(
        directory.join("pl-engine.exe"),
        unpack_engine(EMBEDDED_ENGINE)?,
    )
    .map_err(|_| ERROR)?;
    fs::write(
        directory.join("wintun.dll"),
        include_bytes!(concat!(env!("CARGO_MANIFEST_DIR"), "/engine/wintun.dll")),
    )
    .map_err(|_| ERROR)?;
    let job = Handle(unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) });
    if job.0.is_null() {
        return Err(ERROR);
    }
    unsafe {
        let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if SetInformationJobObject(
            job.0,
            JobObjectExtendedLimitInformation,
            &limits as *const _ as *const _,
            std::mem::size_of_val(&limits) as u32,
        ) == 0
        {
            return Err(ERROR);
        }
    }
    let mut child = Command::new(directory.join("pl-engine.exe"))
        .current_dir(directory)
        .creation_flags(NO_WINDOW)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|_| ERROR)?;
    if unsafe { AssignProcessToJobObject(job.0, child.as_raw_handle()) } == 0 {
        let _ = child.kill();
        let _ = child.wait();
        return Err(ERROR);
    }
    let result = serve_child(pipe, parent, &mut child);
    drop(job); // Force-closes child even if native stop hangs or a reply is lost.
    let _ = child.wait();
    result
}
fn serve_child(pipe: &mut File, parent: &Handle, child: &mut Child) -> Result<(), &'static str> {
    let mut input = child.stdin.take().ok_or(ERROR)?;
    let output = child.stdout.take().ok_or(ERROR)?;
    let (sender, receiver) = mpsc::sync_channel(1);
    std::thread::spawn(move || {
        let mut reader = BufReader::new(output);
        loop {
            let mut data = Vec::new();
            match reader.by_ref().take(4097).read_until(b'\n', &mut data) {
                Ok(n) if n > 0 && n <= 4096 && data.last() == Some(&b'\n') => {
                    if sender.send(data).is_err() {
                        return;
                    }
                }
                _ => return,
            }
        }
    });
    loop {
        let bytes = match frame(pipe, Some(parent), Duration::from_secs(1)) {
            Err("ENGINE_TIMEOUT") => continue,
            other => other?,
        };
        let value: Value = serde_json::from_slice(&bytes).map_err(|_| ERROR)?;
        validate_request(&value)?;
        write_frame(&mut input, &value)?;
        let until = Instant::now() + Duration::from_secs(35);
        let reply = loop {
            if super::vpn_service::stopping() || !running(parent) || Instant::now() >= until {
                return Err(ERROR);
            }
            match receiver.recv_timeout(Duration::from_millis(100)) {
                Ok(data) => break data,
                Err(mpsc::RecvTimeoutError::Timeout) => {}
                Err(_) => return Err(ERROR),
            }
        };
        pipe.write_all(&reply).map_err(|_| ERROR)?;
    }
}

fn validate_request(value: &Value) -> Result<(), &'static str> {
    let object = value.as_object().ok_or(ERROR)?;
    match value["action"].as_str() {
        Some("start") if object.len() == 2 && value["profile"].is_object() => Ok(()),
        Some("stop" | "status" | "direct_location") if object.len() == 1 => Ok(()),
        _ => Err("ENGINE_INVALID_CONFIGURATION"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn embedded_engine_is_a_complete_executable_and_rejects_corruption() {
        let decoded = unpack_engine(EMBEDDED_ENGINE).unwrap();
        assert!(decoded.len() > 1024);
        assert_eq!(&decoded[..2], b"MZ");
        assert!(unpack_engine(&EMBEDDED_ENGINE[..EMBEDDED_ENGINE.len() / 2]).is_err());
        let mut damaged = EMBEDDED_ENGINE.to_vec();
        let last = damaged.len() - 1;
        damaged[last] ^= 1;
        assert!(unpack_engine(&damaged).is_err());
    }

    #[test]
    fn decompression_rejects_non_executable_and_excessive_payload() {
        for data in [vec![0u8; 128], vec![0u8; 64 * 1024 * 1024 + 1]] {
            let mut compressor =
                flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::fast());
            compressor.write_all(&data).unwrap();
            assert!(unpack_engine(&compressor.finish().unwrap()).is_err());
        }
    }

    #[test]
    fn rejects_arbitrary_privileged_commands_and_extra_fields() {
        for request in [
            json!({"action":"exec", "path":"cmd.exe"}),
            json!({"action":"status", "profile":{}}),
            json!({"action":"start", "profile":{}, "args":[]}),
            json!({"action":"start", "profile":"file.conf"}),
        ] {
            assert!(validate_request(&request).is_err());
        }
        for request in [
            json!({"action":"status"}),
            json!({"action":"stop"}),
            json!({"action":"start", "profile":{}}),
        ] {
            assert!(validate_request(&request).is_ok());
        }
    }
    fn test_pipe_name(id: &str) -> String {
        format!(r"\\.\pipe\PrettyLisaVPN-test-{id}")
    }
    #[test]
    fn private_pipe_cannot_be_replaced_and_preserves_frame_boundaries() {
        let id = uuid::Uuid::new_v4().to_string();
        let mut server = pipe_server(&test_pipe_name(&id)).unwrap();
        assert!(pipe_server(&test_pipe_name(&id)).is_err());
        let mut client = OpenOptions::new()
            .read(true)
            .write(true)
            .open(test_pipe_name(&id))
            .unwrap();
        let parent = Handle(unsafe { OpenProcess(SYNCHRONIZE, 0, std::process::id()) });
        assert!(!parent.0.is_null());
        write_frame(&mut client, &json!({"action":"status"})).unwrap();
        write_frame(&mut client, &json!({"action":"stop"})).unwrap();
        for action in ["status", "stop"] {
            let data = frame(&mut server, Some(&parent), Duration::from_secs(2)).unwrap();
            assert_eq!(
                serde_json::from_slice::<Value>(&data).unwrap()["action"],
                action
            );
        }
        drop(client);
        assert!(frame(&mut server, Some(&parent), Duration::from_secs(2)).is_err());
    }

    #[test]
    fn private_pipe_waits_for_delayed_fragmented_frames() {
        let id = uuid::Uuid::new_v4().to_string();
        let mut server = pipe_server(&test_pipe_name(&id)).unwrap();
        let mut client = OpenOptions::new()
            .read(true)
            .write(true)
            .open(test_pipe_name(&id))
            .unwrap();
        let parent = Handle(unsafe { OpenProcess(SYNCHRONIZE, 0, std::process::id()) });
        let writer = std::thread::spawn(move || {
            std::thread::sleep(Duration::from_millis(100));
            client.write_all(b"{\"status\":").unwrap();
            std::thread::sleep(Duration::from_millis(100));
            client.write_all(b"\"RUNNING\"}\n").unwrap();
            client
        });
        let result = frame(&mut server, Some(&parent), Duration::from_secs(2));
        let client = writer.join().unwrap();
        assert_eq!(result.unwrap().as_slice(), b"{\"status\":\"RUNNING\"}");
        assert_eq!(
            frame(&mut server, Some(&parent), Duration::from_millis(100)).unwrap_err(),
            "ENGINE_TIMEOUT"
        );
        drop(client);
        assert_eq!(
            frame(&mut server, Some(&parent), Duration::from_secs(2)).unwrap_err(),
            ERROR
        );
    }

    #[test]
    fn incomplete_frame_timeout_is_fatal_instead_of_discarding_bytes() {
        let id = uuid::Uuid::new_v4().to_string();
        let mut server = pipe_server(&test_pipe_name(&id)).unwrap();
        let mut client = OpenOptions::new()
            .read(true)
            .write(true)
            .open(test_pipe_name(&id))
            .unwrap();
        let parent = Handle(unsafe { OpenProcess(SYNCHRONIZE, 0, std::process::id()) });
        client.write_all(b"{\"action\":").unwrap();
        assert_eq!(
            frame(&mut server, Some(&parent), Duration::from_millis(100)).unwrap_err(),
            "ENGINE_INVALID_RESPONSE"
        );
    }

    #[test]
    fn oversized_frames_never_partially_write() {
        let mut target = Vec::new();
        assert!(write_frame(&mut target, &json!({"profile":"x".repeat(FRAME_LIMIT)})).is_err());
        assert!(target.is_empty());
    }
}
