use std::ffi::OsStr;
use std::os::windows::ffi::OsStrExt;
use windows_sys::Win32::UI::Shell::ShellExecuteW;
use windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;

// Exact host allowlist is configured at build time when a provider is selected.
// No shell, command interpolation, custom URI schemes, or payment URLs in logs.
#[tauri::command]
pub fn open_payment_url(url: String) -> Result<(), &'static str> {
    let parsed = url::Url::parse(&url).map_err(|_| "PAYMENT_URL_NOT_ALLOWED")?;
    let allowed = option_env!("VITE_PAYMENT_ALLOWED_HOSTS").unwrap_or("");
    let permitted = allowed
        .split(',')
        .any(|host| !host.trim().is_empty() && Some(host.trim()) == parsed.host_str());
    if url.len() > 2048
        || parsed.scheme() != "https"
        || !parsed.username().is_empty()
        || parsed.password().is_some()
        || parsed.fragment().is_some()
        || parsed.port_or_known_default() != Some(443)
        || !permitted
    {
        return Err("PAYMENT_URL_NOT_ALLOWED");
    }
    let wide: Vec<u16> = OsStr::new(parsed.as_str())
        .encode_wide()
        .chain(Some(0))
        .collect();
    let verb: Vec<u16> = OsStr::new("open").encode_wide().chain(Some(0)).collect();
    let result = unsafe {
        ShellExecuteW(
            std::ptr::null_mut(),
            verb.as_ptr(),
            wide.as_ptr(),
            std::ptr::null(),
            std::ptr::null(),
            SW_SHOWNORMAL,
        )
    };
    if result as isize <= 32 {
        return Err("PAYMENT_BROWSER_UNAVAILABLE");
    }
    Ok(())
}
