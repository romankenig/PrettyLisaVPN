use tauri::Manager;

/// Clip the real HWND as well as the WebView; works on Windows 10 and 11.
pub fn configure(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let window = app
        .get_webview_window("main")
        .ok_or("Main window unavailable")?;
    round(&window)?;
    let rounded = window.clone();
    window.on_window_event(move |event| {
        if matches!(
            event,
            tauri::WindowEvent::Resized(_) | tauri::WindowEvent::ScaleFactorChanged { .. }
        ) {
            let _ = round(&rounded);
        }
    });
    Ok(())
}

fn round(window: &tauri::WebviewWindow) -> Result<(), Box<dyn std::error::Error>> {
    let size = window.outer_size()?;
    let radius = (12.0 * window.scale_factor()?).round() as i32;
    let hwnd = window.hwnd()?.0;
    unsafe {
        use windows_sys::Win32::Graphics::Gdi::{CreateRoundRectRgn, DeleteObject, SetWindowRgn};
        let region = CreateRoundRectRgn(
            0,
            0,
            size.width as i32 + 1,
            size.height as i32 + 1,
            radius * 2,
            radius * 2,
        );
        if region.is_null() {
            return Err(std::io::Error::last_os_error().into());
        }
        if SetWindowRgn(hwnd, region, 1) == 0 {
            DeleteObject(region);
            return Err(std::io::Error::last_os_error().into());
        }
        // Windows owns the region after a successful SetWindowRgn call.
    }
    Ok(())
}
