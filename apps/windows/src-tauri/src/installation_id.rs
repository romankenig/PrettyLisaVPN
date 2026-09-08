use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use uuid::Uuid;

const INSTALLATION_ID_FILE: &str = "installation-id";

pub struct InstallationIdState(String);

impl InstallationIdState {
    pub fn load(app_config_dir: &Path) -> io::Result<Self> {
        load_or_create(app_config_dir).map(|id| Self(id.to_string()))
    }
}

#[tauri::command]
pub fn get_installation_id(state: tauri::State<'_, InstallationIdState>) -> String {
    state.0.clone()
}

fn load_or_create(app_config_dir: &Path) -> io::Result<Uuid> {
    fs::create_dir_all(app_config_dir)?;
    let path = app_config_dir.join(INSTALLATION_ID_FILE);
    match read(&path) {
        Ok(id) => Ok(id),
        Err(error) if error.kind() == io::ErrorKind::NotFound => create(&path),
        Err(error) => Err(error),
    }
}

fn read(path: &Path) -> io::Result<Uuid> {
    let value = fs::read_to_string(path)?;
    let id = Uuid::parse_str(value.trim()).map_err(|_| invalid_data())?;
    if id.get_version_num() != 4 {
        return Err(invalid_data());
    }
    Ok(id)
}

fn invalid_data() -> io::Error {
    io::Error::new(
        io::ErrorKind::InvalidData,
        "stored installation ID is not a UUID v4",
    )
}

fn create(path: &Path) -> io::Result<Uuid> {
    let id = Uuid::new_v4();
    let temporary = temporary_path(path);
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary)?;
    writeln!(file, "{id}")?;
    file.sync_all()?;
    drop(file);

    match fs::rename(&temporary, path) {
        Ok(()) => Ok(id),
        Err(_) if path.exists() => {
            let _ = fs::remove_file(&temporary);
            read(path)
        }
        Err(error) => {
            let _ = fs::remove_file(&temporary);
            Err(error)
        }
    }
}

fn temporary_path(path: &Path) -> PathBuf {
    path.with_extension(format!("{}.tmp", Uuid::new_v4()))
}

#[cfg(test)]
mod tests {
    use super::*;

    struct TestDirectory(PathBuf);

    impl TestDirectory {
        fn new() -> Self {
            Self(std::env::temp_dir().join(format!(
                "prettylisavpn-installation-id-test-{}",
                Uuid::new_v4()
            )))
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    #[test]
    fn generates_uuid_v4_on_first_launch_and_reuses_it() {
        let directory = TestDirectory::new();

        let first = load_or_create(&directory.0).expect("first launch should create an ID");
        let second = load_or_create(&directory.0).expect("restart should read the stored ID");

        assert_eq!(first.get_version_num(), 4);
        assert_eq!(second, first);
        assert_eq!(
            fs::read_to_string(directory.0.join(INSTALLATION_ID_FILE))
                .expect("installation ID should be persisted")
                .trim(),
            first.to_string()
        );
    }

    #[test]
    fn separate_installations_receive_different_random_ids() {
        let first_directory = TestDirectory::new();
        let second_directory = TestDirectory::new();

        let first = load_or_create(&first_directory.0).expect("first ID should be created");
        let second = load_or_create(&second_directory.0).expect("second ID should be created");

        assert_ne!(first, second);
    }

    #[test]
    fn invalid_persisted_value_is_rejected_without_replacement() {
        let directory = TestDirectory::new();
        fs::create_dir_all(&directory.0).expect("test directory should be created");
        let path = directory.0.join(INSTALLATION_ID_FILE);
        fs::write(&path, "not-a-uuid\n").expect("invalid fixture should be written");

        let error = load_or_create(&directory.0).expect_err("invalid ID should fail closed");

        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert_eq!(fs::read_to_string(path).unwrap(), "not-a-uuid\n");
    }
}
