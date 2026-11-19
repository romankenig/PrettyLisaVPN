fn main() {
    println!("cargo:rerun-if-env-changed=VITE_BACKEND_BASE_URL");
    let api = std::env::var("VITE_BACKEND_BASE_URL").unwrap_or_default();
    let (api_host, website_host) = if api == "https://api.test.prettylisavpn.com" {
        ("api.test.prettylisavpn.com", "test.prettylisavpn.com")
    } else {
        ("api.prettylisavpn.com", "prettylisavpn.com")
    };
    println!("cargo:rustc-env=PRETTYLISA_API_HOST={api_host}");
    println!("cargo:rustc-env=PRETTYLISA_WEBSITE_HOST={website_host}");
    tauri_build::build();
}
