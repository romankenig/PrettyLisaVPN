#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod installation_id;
mod managed;
mod payment_browser;
mod public_location;
mod refresh_credentials;
mod window_frame;
mod wireguard;

use tauri::Manager;

fn main() {
    let arguments: Vec<String> = std::env::args().collect();
    if arguments
        .get(1)
        .is_some_and(|value| value == "--engine-host")
    {
        std::process::exit(if managed::host(&arguments).is_ok() {
            0
        } else {
            1
        });
    }
    tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .setup(|app| {
            window_frame::configure(app)?;
            let app_config_dir = app.path().app_config_dir()?;
            let installation_id = installation_id::InstallationIdState::load(&app_config_dir)?;
            app.manage(installation_id);
            app.manage(refresh_credentials::RefreshCredentialState::new());
            app.manage(wireguard::WireGuardState::default());
            app.manage(managed::ManagedState::default());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            payment_browser::open_payment_url,
            public_location::get_public_location,
            public_location::get_vpn_location,
            installation_id::get_installation_id,
            refresh_credentials::save_refresh_credential,
            refresh_credentials::load_refresh_credential,
            refresh_credentials::replace_refresh_credential,
            refresh_credentials::delete_refresh_credential,
            wireguard::wg_prepare,
            wireguard::wg_start,
            wireguard::wg_start_routed,
            wireguard::wg_stop,
            wireguard::wg_is_up,
            wireguard::wg_verify,
            managed::engine_start,
            managed::engine_stop,
            managed::engine_is_up,
            managed::engine_verify,
        ])
        .run(tauri::generate_context!())
        .expect("Unable to start PrettyLisaVPN");
}
