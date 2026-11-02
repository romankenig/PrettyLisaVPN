//! Installer-owned LocalSystem service. The GUI never elevates itself.
use std::{
    ffi::OsStr,
    os::windows::ffi::OsStrExt,
    path::PathBuf,
    ptr,
    sync::atomic::{AtomicBool, AtomicPtr, Ordering},
    time::{Duration, Instant},
};
use windows_sys::Win32::{
    Foundation::*,
    System::{Com::CoTaskMemFree, Services::*},
    UI::Shell::{FOLDERID_ProgramFiles, SHGetKnownFolderPath},
};

pub const NAME: &str = "PrettyLisaVPNService";
pub const PIPE: &str = r"\\.\pipe\PrettyLisaVPN-Service-v1";
pub const ERROR: &str = "VPN_SERVICE_UNAVAILABLE";
static STOPPING: AtomicBool = AtomicBool::new(false);
static STATUS: AtomicPtr<std::ffi::c_void> = AtomicPtr::new(ptr::null_mut());

pub fn wide(value: impl AsRef<OsStr>) -> Vec<u16> {
    value.as_ref().encode_wide().chain(Some(0)).collect()
}
pub fn stopping() -> bool {
    STOPPING.load(Ordering::Acquire)
}
struct ScHandle(SC_HANDLE);
impl Drop for ScHandle {
    fn drop(&mut self) {
        unsafe {
            CloseServiceHandle(self.0);
        }
    }
}
fn manager(access: u32) -> Result<ScHandle, &'static str> {
    let h = unsafe { OpenSCManagerW(ptr::null(), ptr::null(), access) };
    if h.is_null() {
        Err(ERROR)
    } else {
        Ok(ScHandle(h))
    }
}
fn status(service: &ScHandle) -> Result<SERVICE_STATUS_PROCESS, &'static str> {
    let mut value: SERVICE_STATUS_PROCESS = unsafe { std::mem::zeroed() };
    let mut needed = 0;
    if unsafe {
        QueryServiceStatusEx(
            service.0,
            SC_STATUS_PROCESS_INFO,
            &mut value as *mut _ as *mut u8,
            std::mem::size_of_val(&value) as u32,
            &mut needed,
        )
    } == 0
    {
        return Err(ERROR);
    }
    Ok(value)
}
pub fn process_id() -> Result<Option<u32>, &'static str> {
    let scm = manager(SC_MANAGER_CONNECT)?;
    let handle = unsafe { OpenServiceW(scm.0, wide(NAME).as_ptr(), SERVICE_QUERY_STATUS) };
    if handle.is_null() {
        return if unsafe { GetLastError() } == ERROR_SERVICE_DOES_NOT_EXIST {
            Ok(None)
        } else {
            Err(ERROR)
        };
    }
    let value = status(&ScHandle(handle))?;
    match value.dwCurrentState {
        SERVICE_STOPPED => Ok(None),
        SERVICE_RUNNING if value.dwProcessId != 0 => Ok(Some(value.dwProcessId)),
        _ => Err(ERROR), // Never treat a pending stop/start as confirmed cleanup.
    }
}
pub fn installed_executable() -> Result<PathBuf, &'static str> {
    unsafe {
        let mut path = ptr::null_mut();
        if SHGetKnownFolderPath(&FOLDERID_ProgramFiles, 0, ptr::null_mut(), &mut path) < 0 {
            return Err(ERROR);
        }
        let mut length = 0;
        while *path.add(length) != 0 {
            length += 1;
        }
        let value = String::from_utf16(std::slice::from_raw_parts(path, length));
        CoTaskMemFree(path as _);
        Ok(PathBuf::from(value.map_err(|_| ERROR)?)
            .join("PrettyLisaVPN")
            .join("prettylisavpn-windows.exe"))
    }
}
fn ensure_installed_path() -> Result<(), &'static str> {
    let expected = installed_executable()?;
    let actual = std::env::current_exe().map_err(|_| ERROR)?;
    // Reject alternate directories and reparse targets, including redirected parents.
    if actual != expected
        || std::fs::canonicalize(&actual).map_err(|_| ERROR)?
            != std::path::Path::new(&format!(r"\\?\{}", expected.display()))
    {
        return Err(ERROR);
    }
    Ok(())
}
pub fn install() -> Result<(), &'static str> {
    ensure_installed_path()?;
    let scm = manager(SC_MANAGER_CREATE_SERVICE)?;
    let binary = wide(format!(
        "\"{}\" --vpn-service",
        installed_executable()?.display()
    ));
    let handle = unsafe {
        CreateServiceW(
            scm.0,
            wide(NAME).as_ptr(),
            wide("PrettyLisaVPN connection service").as_ptr(),
            SERVICE_START | SERVICE_QUERY_STATUS | 0x00010000,
            SERVICE_WIN32_OWN_PROCESS,
            SERVICE_AUTO_START,
            SERVICE_ERROR_NORMAL,
            binary.as_ptr(),
            ptr::null(),
            ptr::null_mut(),
            ptr::null(),
            ptr::null(),
            ptr::null(),
        )
    };
    if handle.is_null() {
        return Err(ERROR);
    }
    let service = ScHandle(handle);
    if unsafe { StartServiceW(service.0, 0, ptr::null()) } == 0 {
        unsafe {
            DeleteService(service.0);
        }
        return Err(ERROR);
    }
    let until = Instant::now() + Duration::from_secs(20);
    while Instant::now() < until {
        if status(&service)?.dwCurrentState == SERVICE_RUNNING {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    Err(ERROR)
}
fn report(state: u32) {
    let value = SERVICE_STATUS {
        dwServiceType: SERVICE_WIN32_OWN_PROCESS,
        dwCurrentState: state,
        dwControlsAccepted: if state == SERVICE_RUNNING {
            SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN
        } else {
            0
        },
        dwWin32ExitCode: 0,
        dwServiceSpecificExitCode: 0,
        dwCheckPoint: if state == SERVICE_STOP_PENDING { 1 } else { 0 },
        dwWaitHint: if state == SERVICE_STOP_PENDING {
            10000
        } else {
            0
        },
    };
    unsafe {
        SetServiceStatus(STATUS.load(Ordering::Acquire), &value);
    }
}
unsafe extern "system" fn control(code: u32) {
    if code == SERVICE_CONTROL_STOP || code == SERVICE_CONTROL_SHUTDOWN {
        STOPPING.store(true, Ordering::Release);
        report(SERVICE_STOP_PENDING);
    }
}
unsafe extern "system" fn service_main(_: u32, _: *mut *mut u16) {
    let handle = RegisterServiceCtrlHandlerW(wide(NAME).as_ptr(), Some(control));
    if handle.is_null() {
        return;
    }
    STATUS.store(handle, Ordering::Release);
    // Announce readiness only after acquiring the unique local pipe.
    if super::managed::serve_service(|| report(SERVICE_RUNNING)).is_err() {
        // No profiles, credentials or URLs are written to service logs.
        report(SERVICE_STOPPED);
        std::process::exit(1);
    }
    report(SERVICE_STOPPED);
}
pub fn dispatch() -> Result<(), &'static str> {
    ensure_installed_path()?;
    let mut name = wide(NAME);
    let table = [
        SERVICE_TABLE_ENTRYW {
            lpServiceName: name.as_mut_ptr(),
            lpServiceProc: Some(service_main),
        },
        SERVICE_TABLE_ENTRYW {
            lpServiceName: ptr::null_mut(),
            lpServiceProc: None,
        },
    ];
    if unsafe { StartServiceCtrlDispatcherW(table.as_ptr()) } == 0 {
        Err(ERROR)
    } else {
        Ok(())
    }
}
