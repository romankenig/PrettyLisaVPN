#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod demo_identity;
mod installation_id;
mod managed;
mod payment_browser;
mod public_documents;
mod public_location;
mod refresh_credentials;
mod vpn_handoff;
mod vpn_service;
mod window_frame;
mod wireguard;

use tauri::Manager;

fn main() {
    let arguments: Vec<String> = std::env::args().collect();
    let action = match arguments.get(1).map(String::as_str) {
        Some("--vpn-service") if arguments.len() == 2 => Some(vpn_service::dispatch()),
        Some("--install-service") if arguments.len() == 2 => Some(vpn_service::install()),
        Some("--service-check") if arguments.len() == 2 => Some(managed::service_check()),
        _ => None,
    };
    if let Some(result) = action {
        if let Err(code) = result {
            eprintln!("{code}: {}", std::io::Error::last_os_error());
        }
        std::process::exit(if result.is_ok() { 0 } else { 1 });
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
            demo_identity::get_demo_device_key,
            public_documents::open_public_document,
            public_location::get_public_location,
            public_location::get_vpn_location,
            public_location::get_direct_location,
            installation_id::get_installation_id,
            refresh_credentials::save_refresh_credential,
            refresh_credentials::load_refresh_credential,
            refresh_credentials::replace_refresh_credential,
            refresh_credentials::delete_refresh_credential,
            vpn_handoff::vpn_handoff,
            wireguard::wg_prepare,
            wireguard::wg_start_routed,
            wireguard::wg_stop,
            managed::engine_start,
            managed::engine_stop,
            managed::engine_is_up,
            managed::engine_verify,
        ])
        .run(tauri::generate_context!())
        .expect("Unable to start PrettyLisaVPN");
}
