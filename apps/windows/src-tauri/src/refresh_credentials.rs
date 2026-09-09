use std::io;
use std::ptr;
use std::slice;

use serde::{Deserialize, Serialize};
use uuid::Uuid;
use windows_sys::Win32::Foundation::{GetLastError, ERROR_NOT_FOUND};
use windows_sys::Win32::Security::Credentials::{
    CredDeleteW, CredFree, CredReadW, CredWriteW, CREDENTIALW, CRED_PERSIST_LOCAL_MACHINE,
    CRED_TYPE_GENERIC,
};
use zeroize::{Zeroize, Zeroizing};

const CREDENTIAL_TARGET: &str = "PrettyLisaVPN/auth/refresh-token/v1";
const MAX_REFRESH_TOKEN_BYTES: usize = 512;
const STORAGE_ERROR: &str = "credential_storage_unavailable";

#[derive(Deserialize)]
pub struct RefreshCredentialInput {
    session_id: String,
    refresh_token: String,
    expires_at: String,
}

impl Drop for RefreshCredentialInput {
    fn drop(&mut self) {
        self.refresh_token.zeroize();
    }
}

#[derive(Serialize)]
pub struct StoredRefreshCredential {
    session_id: String,
    refresh_token: String,
    expires_at: String,
}

impl Drop for StoredRefreshCredential {
    fn drop(&mut self) {
        self.refresh_token.zeroize();
    }
}

pub struct RefreshCredentialState {
    target: String,
}

impl RefreshCredentialState {
    pub fn new() -> Self {
        Self {
            target: CREDENTIAL_TARGET.to_owned(),
        }
    }

    fn write(&self, mut input: RefreshCredentialInput) -> io::Result<()> {
        validate(&input)?;
        let session_id = std::mem::take(&mut input.session_id);
        let refresh_token = Zeroizing::new(std::mem::take(&mut input.refresh_token));
        let expires_at = std::mem::take(&mut input.expires_at);
        let mut target = wide(&self.target);
        let mut username = wide(&session_id);
        let mut comment = wide(&expires_at);
        let blob_size = u32::try_from(refresh_token.len()).map_err(|_| invalid_input())?;
        let credential = CREDENTIALW {
            Type: CRED_TYPE_GENERIC,
            TargetName: target.as_mut_ptr(),
            Comment: comment.as_mut_ptr(),
            CredentialBlobSize: blob_size,
            CredentialBlob: refresh_token.as_ptr().cast_mut(),
            Persist: CRED_PERSIST_LOCAL_MACHINE,
            UserName: username.as_mut_ptr(),
            ..Default::default()
        };

        // SAFETY: all pointers reference live buffers for the duration of the call.
        if unsafe { CredWriteW(&credential, 0) } == 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(())
    }

    fn read(&self) -> io::Result<Option<StoredRefreshCredential>> {
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
        if blob_length == 0 || blob_length > MAX_REFRESH_TOKEN_BYTES {
            return Err(invalid_data());
        }
        // SAFETY: CredentialBlob points to CredentialBlobSize bytes while the guard is alive.
        let blob = Zeroizing::new(unsafe {
            slice::from_raw_parts(credential.CredentialBlob, blob_length).to_vec()
        });
        let refresh_token = String::from_utf8(blob.to_vec()).map_err(|_| invalid_data())?;
        let session_id = read_wide(credential.UserName)?;
        let expires_at = read_wide(credential.Comment)?;
        let mut stored = RefreshCredentialInput {
            session_id,
            refresh_token,
            expires_at,
        };
        validate(&stored).map_err(|_| invalid_data())?;
        Ok(Some(StoredRefreshCredential {
            session_id: std::mem::take(&mut stored.session_id),
            refresh_token: std::mem::take(&mut stored.refresh_token),
            expires_at: std::mem::take(&mut stored.expires_at),
        }))
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
pub fn save_refresh_credential(
    state: tauri::State<'_, RefreshCredentialState>,
    credential: RefreshCredentialInput,
) -> Result<(), &'static str> {
    state.write(credential).map_err(|_| STORAGE_ERROR)
}

#[tauri::command]
pub fn load_refresh_credential(
    state: tauri::State<'_, RefreshCredentialState>,
) -> Result<Option<StoredRefreshCredential>, &'static str> {
    state.read().map_err(|_| STORAGE_ERROR)
}

#[tauri::command]
pub fn replace_refresh_credential(
    state: tauri::State<'_, RefreshCredentialState>,
    credential: RefreshCredentialInput,
) -> Result<(), &'static str> {
    state.write(credential).map_err(|_| STORAGE_ERROR)
}

#[tauri::command]
pub fn delete_refresh_credential(
    state: tauri::State<'_, RefreshCredentialState>,
) -> Result<(), &'static str> {
    state.delete().map_err(|_| STORAGE_ERROR)
}

fn validate(input: &RefreshCredentialInput) -> io::Result<()> {
    Uuid::parse_str(&input.session_id).map_err(|_| invalid_input())?;
    if input.refresh_token.is_empty()
        || input.refresh_token.len() > MAX_REFRESH_TOKEN_BYTES
        || input.expires_at.trim().is_empty()
    {
        return Err(invalid_input());
    }
    Ok(())
}

fn wide(value: &str) -> Vec<u16> {
    value.encode_utf16().chain(Some(0)).collect()
}

fn read_wide(pointer: *const u16) -> io::Result<String> {
    if pointer.is_null() {
        return Err(invalid_data());
    }
    let mut length = 0usize;
    // Credential Manager strings are NUL-terminated. Bound the scan to reject corrupt data.
    while length < 32_768 {
        // SAFETY: the pointer belongs to a live Credential Manager allocation.
        if unsafe { *pointer.add(length) } == 0 {
            // SAFETY: the preceding elements were scanned from the same live allocation.
            return String::from_utf16(unsafe { slice::from_raw_parts(pointer, length) })
                .map_err(|_| invalid_data());
        }
        length += 1;
    }
    Err(invalid_data())
}

fn invalid_input() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, "invalid credential input")
}

fn invalid_data() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, "invalid stored credential")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn input() -> RefreshCredentialInput {
        RefreshCredentialInput {
            session_id: Uuid::new_v4().to_string(),
            refresh_token: "test-refresh-token".to_owned(),
            expires_at: "2026-10-09T00:00:00Z".to_owned(),
        }
    }

    #[test]
    fn validates_safe_credential_bounds() {
        assert!(validate(&input()).is_ok());
        let mut empty = input();
        empty.refresh_token.clear();
        assert_eq!(
            validate(&empty).unwrap_err().kind(),
            io::ErrorKind::InvalidInput
        );
        let mut oversized = input();
        oversized.refresh_token = "x".repeat(MAX_REFRESH_TOKEN_BYTES + 1);
        assert_eq!(
            validate(&oversized).unwrap_err().kind(),
            io::ErrorKind::InvalidInput
        );
    }

    #[test]
    fn rejects_invalid_session_metadata() {
        let mut value = input();
        value.session_id = "not-a-uuid".to_owned();
        assert_eq!(
            validate(&value).unwrap_err().kind(),
            io::ErrorKind::InvalidInput
        );
    }

    #[test]
    fn windows_credential_manager_round_trip_replace_and_delete() {
        let store = RefreshCredentialState {
            target: format!("PrettyLisaVPN/test/{}", Uuid::new_v4()),
        };
        let first = input();
        let first_session = first.session_id.clone();
        store.write(first).expect("test credential should be saved");

        let loaded = store.read().expect("test credential should load").unwrap();
        assert_eq!(loaded.session_id, first_session);
        assert_eq!(loaded.refresh_token, "test-refresh-token");

        let mut replacement = input();
        replacement.refresh_token = "replacement-token".to_owned();
        store
            .write(replacement)
            .expect("credential should be replaced");
        assert_eq!(
            store.read().unwrap().unwrap().refresh_token,
            "replacement-token"
        );

        store.delete().expect("test credential should be deleted");
        assert!(store
            .read()
            .expect("missing credential should be valid")
            .is_none());
        store.delete().expect("delete should be idempotent");
    }
}
