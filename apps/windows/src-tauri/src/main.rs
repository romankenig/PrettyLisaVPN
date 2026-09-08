#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod installation_id;

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .setup(|app| {
            let app_config_dir = app.path().app_config_dir()?;
            let installation_id = installation_id::InstallationIdState::load(&app_config_dir)?;
            app.manage(installation_id);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            installation_id::get_installation_id
        ])
        .run(tauri::generate_context!())
        .expect("Unable to start PrettyLisaVPN");
}
