#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

#[tauri::command]
fn write_tex_note_file(path: String, content: String) -> Result<String, String> {
    let trimmed_path = path.trim();
    if trimmed_path.is_empty() {
        return Err("Export path is required.".to_string());
    }
    if !trimmed_path.to_ascii_lowercase().ends_with(".tex") {
        return Err("Export path must end with .tex.".to_string());
    }

    let export_path = std::path::Path::new(trimmed_path);
    if export_path.is_dir() {
        return Err("Export path points to a directory, not a .tex file.".to_string());
    }

    std::fs::write(export_path, content)
        .map_err(|error| format!("Could not write LaTeX note file: {error}"))?;

    Ok(trimmed_path.to_string())
}

fn main() {
    let mut context = tauri::generate_context!();
    context.set_default_window_icon(None);

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![write_tex_note_file])
        .run(context)
        .expect("error while running tauri application");
}
