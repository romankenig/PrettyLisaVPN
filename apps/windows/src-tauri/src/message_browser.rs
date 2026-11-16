use std::ffi::OsStr;
use std::os::windows::ffi::OsStrExt;
use windows_sys::Win32::UI::Shell::ShellExecuteW;
use windows_sys::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;

fn validated_url(raw: &str) -> Result<url::Url, &'static str> {
    let invalid = "MESSAGE_URL_NOT_ALLOWED";
    if raw.len() > 2048
        || !raw.starts_with("https://")
        || raw
            .chars()
            .any(|c| c.is_whitespace() || c.is_control() || c == '\\')
        || raw[8..]
            .split(['/', '?', '#'])
            .next()
            .unwrap_or("")
            .contains('@')
    {
        return Err(invalid);
    }
    let parsed = url::Url::parse(raw).map_err(|_| invalid)?;
    if parsed.host_str().is_none()
        || !parsed.username().is_empty()
        || parsed.password().is_some()
        || parsed.port_or_known_default() != Some(443)
    {
        return Err(invalid);
    }
    Ok(parsed)
}

// Separate from payment hosts. Only explicit clicks open operator-authored HTTPS
// links; never execute shell commands, attach tokens or log message contents/URLs.
#[tauri::command]
pub fn open_message_url(url: String) -> Result<(), &'static str> {
    let parsed = validated_url(&url)?;
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
        return Err("MESSAGE_BROWSER_UNAVAILABLE");
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_unambiguous_https_links() {
        assert!(
            validated_url("https://prettylisavpn.com/download?platform=windows#latest").is_ok()
        );
        for raw in [
            "http://example.com",
            "file:///tmp/x",
            "javascript:alert(1)",
            "https://user@example.com",
            "https://@example.com",
            "https://example.com:8443",
            "https://example.com\\@evil.com",
            "https://example.com/\n",
        ] {
            assert!(validated_url(raw).is_err());
        }
    }
}
