use std::io;
use std::ptr;
use std::slice;

use base64::engine::general_purpose::STANDARD;
use base64::Engine;
use rand_core::OsRng;
use serde::Serialize;
use windows_sys::Win32::Foundation::{GetLastError, ERROR_NOT_FOUND};
use windows_sys::Win32::Security::Credentials::{
    CredDeleteW, CredFree, CredReadW, CredWriteW, CREDENTIALW, CRED_PERSIST_LOCAL_MACHINE,
    CRED_TYPE_GENERIC,
};
use x25519_dalek::{PublicKey, StaticSecret};
use zeroize::Zeroizing;

const CREDENTIAL_TARGET: &str = "PrettyLisaVPN/vpn/wireguard/private-key/v1";
const PRIVATE_KEY_BYTES: usize = 32;
const STORAGE_ERROR: &str = "wireguard_key_storage_unavailable";

#[derive(Serialize)]
pub struct WireGuardPublicKey {
    public_key: String,
}

pub struct WireGuardKeyState {
    target: String,
}

impl WireGuardKeyState {
    pub fn new() -> Self {
        Self {
            target: CREDENTIAL_TARGET.to_owned(),
        }
    }

    fn ensure_public_key(&self) -> io::Result<WireGuardPublicKey> {
        let private_key = match self.read_private_key()? {
            Some(private_key) => private_key,
            None => {
                let generated = StaticSecret::random_from_rng(OsRng);
                let private_key = Zeroizing::new(generated.to_bytes());
                self.write_private_key(&private_key)?;
                private_key
            }
        };
        Ok(WireGuardPublicKey {
            public_key: derive_public_key(&private_key),
        })
    }

    fn load_public_key(&self) -> io::Result<Option<WireGuardPublicKey>> {
        Ok(self
            .read_private_key()?
            .map(|private_key| WireGuardPublicKey {
                public_key: derive_public_key(&private_key),
            }))
    }

    fn write_private_key(&self, private_key: &[u8; PRIVATE_KEY_BYTES]) -> io::Result<()> {
        let mut target = wide(&self.target);
        let blob_size = u32::try_from(PRIVATE_KEY_BYTES).map_err(|_| invalid_data())?;
        let credential = CREDENTIALW {
            Type: CRED_TYPE_GENERIC,
            TargetName: target.as_mut_ptr(),
            CredentialBlobSize: blob_size,
            CredentialBlob: private_key.as_ptr().cast_mut(),
            Persist: CRED_PERSIST_LOCAL_MACHINE,
            ..Default::default()
        };

        // SAFETY: all pointers reference live buffers for the duration of the call.
        if unsafe { CredWriteW(&credential, 0) } == 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(())
    }

    fn read_private_key(&self) -> io::Result<Option<Zeroizing<[u8; PRIVATE_KEY_BYTES]>>> {
        let target = wide(&self.target);
        let mut raw = ptr::null_mut();
        // SAFETY: target is NUL-terminated and raw is a valid output pointer.
        if unsafe { CredReadW(target.as_ptr(), CRED_TYPE_GENERIC, 0, &mut raw) } == 0 {
            // SAFETY: GetLastError immediately follows the failing Win32 call.
            if unsafe { GetLastError() } == ERROR_NOT_FOUND {
                return Ok(None);
            }
            return Err(io::Error::last_os_error());
        }
        let credential = CredentialGuard(raw);
        // SAFETY: CredReadW returned a valid CREDENTIALW owned by CredentialGuard.
        let credential = unsafe { &*credential.0 };
        let blob_length =
            usize::try_from(credential.CredentialBlobSize).map_err(|_| invalid_data())?;
        if blob_length != PRIVATE_KEY_BYTES || credential.CredentialBlob.is_null() {
            return Err(invalid_data());
        }
        // SAFETY: CredentialBlob points to exactly CredentialBlobSize bytes while guarded.
        let bytes = unsafe { slice::from_raw_parts(credential.CredentialBlob, blob_length) };
        let mut private_key = Zeroizing::new([0_u8; PRIVATE_KEY_BYTES]);
        private_key.copy_from_slice(bytes);
        Ok(Some(private_key))
    }

    fn delete(&self) -> io::Result<()> {
        let target = wide(&self.target);
        // SAFETY: target is a live NUL-terminated UTF-16 buffer.
        if unsafe { CredDeleteW(target.as_ptr(), CRED_TYPE_GENERIC, 0) } == 0 {
            // SAFETY: GetLastError immediately follows the failing Win32 call.
            if unsafe { GetLastError() } != ERROR_NOT_FOUND {
                return Err(io::Error::last_os_error());
            }
        }
        Ok(())
    }
}

struct CredentialGuard(*mut CREDENTIALW);

impl Drop for CredentialGuard {
    fn drop(&mut self) {
        // SAFETY: this pointer was allocated by CredReadW and is freed exactly once.
        unsafe { CredFree(self.0.cast()) };
    }
}

#[tauri::command]
pub fn ensure_wireguard_public_key(
    state: tauri::State<'_, WireGuardKeyState>,
) -> Result<WireGuardPublicKey, &'static str> {
    state.ensure_public_key().map_err(|_| STORAGE_ERROR)
}

#[tauri::command]
pub fn load_wireguard_public_key(
    state: tauri::State<'_, WireGuardKeyState>,
) -> Result<Option<WireGuardPublicKey>, &'static str> {
    state.load_public_key().map_err(|_| STORAGE_ERROR)
}

#[tauri::command]
pub fn delete_wireguard_key(
    state: tauri::State<'_, WireGuardKeyState>,
) -> Result<(), &'static str> {
    state.delete().map_err(|_| STORAGE_ERROR)
}

fn derive_public_key(private_key: &[u8; PRIVATE_KEY_BYTES]) -> String {
    let private = StaticSecret::from(*private_key);
    STANDARD.encode(PublicKey::from(&private).as_bytes())
}

fn wide(value: &str) -> Vec<u16> {
    value.encode_utf16().chain(Some(0)).collect()
}

fn invalid_data() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, "invalid WireGuard key material")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generates_distinct_valid_wireguard_keypairs() {
        let first = StaticSecret::random_from_rng(OsRng);
        let second = StaticSecret::random_from_rng(OsRng);

        let first_public = derive_public_key(&first.to_bytes());
        let second_public = derive_public_key(&second.to_bytes());

        assert_eq!(STANDARD.decode(&first_public).unwrap().len(), 32);
        assert_ne!(first.to_bytes(), second.to_bytes());
        assert_ne!(first_public, second_public);
    }

    #[test]
    fn derives_rfc_7748_alice_public_key() {
        let private_key =
            hex_to_array("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a");
        let expected =
            hex_to_array("8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a");

        assert_eq!(
            STANDARD.decode(derive_public_key(&private_key)).unwrap(),
            expected
        );
    }

    #[test]
    fn windows_credential_manager_persists_private_key_without_exposing_it() {
        let store = WireGuardKeyState {
            target: format!("PrettyLisaVPN/test/wireguard/{}", uuid::Uuid::new_v4()),
        };
        let first = store
            .ensure_public_key()
            .expect("keypair should be created");
        let loaded = store
            .load_public_key()
            .expect("keypair should load")
            .expect("keypair should exist");

        assert_eq!(first.public_key, loaded.public_key);
        assert_eq!(STANDARD.decode(&loaded.public_key).unwrap().len(), 32);
        store.delete().expect("keypair should delete");
        assert!(store.load_public_key().unwrap().is_none());
        store.delete().expect("delete should be idempotent");
    }

    fn hex_to_array(value: &str) -> [u8; PRIVATE_KEY_BYTES] {
        let mut output = [0_u8; PRIVATE_KEY_BYTES];
        for (index, chunk) in value.as_bytes().chunks_exact(2).enumerate() {
            output[index] = u8::from_str_radix(std::str::from_utf8(chunk).unwrap(), 16).unwrap();
        }
        output
    }
}
