#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod debug_log;
mod installation_id;
mod internet_verification;
mod obfuscation_transport;
mod packet_obfuscation;
mod payment_browser;
mod refresh_credentials;
mod wg_obfuscator;
mod window_frame;
mod wireguard_keys;
mod wireguard_tunnel;

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .setup(|app| {
            window_frame::configure(app)?;
            let app_config_dir = app.path().app_config_dir()?;
            let installation_id = installation_id::InstallationIdState::load(&app_config_dir)?;
            app.manage(installation_id);
            app.manage(refresh_credentials::RefreshCredentialState::new());
            app.manage(wireguard_keys::WireGuardKeyState::new());
            app.manage(wireguard_tunnel::WireGuardTunnelState::new());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            payment_browser::open_payment_url,
            installation_id::get_installation_id,
            refresh_credentials::save_refresh_credential,
            refresh_credentials::load_refresh_credential,
            refresh_credentials::replace_refresh_credential,
            refresh_credentials::delete_refresh_credential,
            wireguard_keys::ensure_wireguard_public_key,
            wireguard_keys::load_wireguard_public_key,
            wireguard_keys::delete_wireguard_key,
            wireguard_tunnel::start_wireguard_tunnel,
            wireguard_tunnel::verify_wireguard_internet,
            wireguard_tunnel::stop_wireguard_tunnel,
            wireguard_tunnel::get_wireguard_tunnel_state,
            wireguard_tunnel::get_wireguard_peer_diagnostics,
        ])
        .run(tauri::generate_context!())
        .expect("Unable to start PrettyLisaVPN");
}
