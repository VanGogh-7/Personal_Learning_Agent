#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    let mut context = tauri::generate_context!();
    context.set_default_window_icon(None);

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .run(context)
        .expect("error while running tauri application");
}
