//! Safe native VPN diagnostics for development and explicit troubleshooting.

use std::fmt;
use std::sync::OnceLock;
use std::time::{SystemTime, UNIX_EPOCH};

const DEBUG_ENV: &str = "PRETTYLISA_VPN_DEBUG";

pub(crate) fn enabled() -> bool {
    static ENABLED: OnceLock<bool> = OnceLock::new();
    *ENABLED.get_or_init(|| {
        cfg!(debug_assertions)
            || std::env::var(DEBUG_ENV)
                .map(|value| matches!(value.as_str(), "1" | "true" | "TRUE" | "yes" | "YES"))
                .unwrap_or(false)
    })
}

pub(crate) fn event(name: &str, fields: fmt::Arguments<'_>) {
    if !enabled() {
        return;
    }
    let timestamp_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default();
    eprintln!("vpn_debug ts_ms={timestamp_ms} event={name} {fields}");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn debug_builds_enable_safe_native_diagnostics() {
        assert!(enabled());
    }
}
