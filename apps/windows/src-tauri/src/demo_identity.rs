//! Reinstall-stable, app-scoped guest identity. Raw OS identity never leaves native code.
use sha2::{Digest, Sha256};
use windows_sys::Win32::System::Registry::{
    RegGetValueW, HKEY_LOCAL_MACHINE, RRF_RT_REG_SZ, RRF_SUBKEY_WOW6464KEY,
};
use zeroize::Zeroizing;

fn scoped_hash(raw: &str) -> Result<String, &'static str> {
    let id = uuid::Uuid::parse_str(raw.trim()).map_err(|_| "DEMO_IDENTITY_UNAVAILABLE")?;
    if id.is_nil() {
        return Err("DEMO_IDENTITY_UNAVAILABLE");
    }
    let normalized = Zeroizing::new(id.to_string());
    let mut hash = Sha256::new();
    hash.update(b"PrettyLisaVPN/windows/demo/v1\0");
    hash.update(normalized.as_bytes());
    Ok(format!("{:x}", hash.finalize()))
}

#[tauri::command]
pub fn get_demo_device_key() -> Result<String, &'static str> {
    let key: Vec<u16> = "SOFTWARE\\Microsoft\\Cryptography\0"
        .encode_utf16()
        .collect();
    let name: Vec<u16> = "MachineGuid\0".encode_utf16().collect();
    let mut buffer = Zeroizing::new([0u16; 128]);
    let mut size = std::mem::size_of_val(buffer.as_ref()) as u32;
    let result = unsafe {
        RegGetValueW(
            HKEY_LOCAL_MACHINE,
            key.as_ptr(),
            name.as_ptr(),
            RRF_RT_REG_SZ | RRF_SUBKEY_WOW6464KEY,
            std::ptr::null_mut(),
            buffer.as_mut_ptr().cast(),
            &mut size,
        )
    };
    if result != 0 || size < 2 || size as usize > buffer.len() * 2 || size % 2 != 0 {
        return Err("DEMO_IDENTITY_UNAVAILABLE");
    }
    let raw = Zeroizing::new(
        String::from_utf16(&buffer[..size as usize / 2 - 1])
            .map_err(|_| "DEMO_IDENTITY_UNAVAILABLE")?,
    );
    scoped_hash(&raw)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn stable_normalized_scoped_identity_and_fail_closed() {
        let a = scoped_hash("ABCDEF01-2345-4678-9ABC-DEF012345678").unwrap();
        assert_eq!(
            a,
            scoped_hash("abcdef01-2345-4678-9abc-def012345678").unwrap()
        );
        assert_eq!(a.len(), 64);
        assert_ne!(
            a,
            scoped_hash("abcdef02-2345-4678-9abc-def012345678").unwrap()
        );
        for invalid in ["", "random", "00000000-0000-0000-0000-000000000000"] {
            assert!(scoped_hash(invalid).is_err());
        }
    }
}
