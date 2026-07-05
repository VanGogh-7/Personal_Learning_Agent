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

#[tauri::command]
fn export_tex_note_to_workspace(
    workspace_path: String,
    filename: String,
    content: String,
) -> Result<String, String> {
    let trimmed_workspace_path = workspace_path.trim();
    if trimmed_workspace_path.is_empty() {
        return Err("Workspace path is required.".to_string());
    }

    let workspace = std::path::Path::new(trimmed_workspace_path);
    if !workspace.is_dir() {
        return Err("Workspace path must be an existing directory.".to_string());
    }

    let safe_filename = validate_tex_filename(filename.trim())?;
    let export_path = unique_workspace_path(workspace, &safe_filename);

    std::fs::write(&export_path, content)
        .map_err(|error| format!("Could not export note to workspace: {error}"))?;

    Ok(export_path.to_string_lossy().to_string())
}

fn validate_tex_filename(filename: &str) -> Result<String, String> {
    if filename.is_empty() {
        return Err("Export filename is required.".to_string());
    }
    if !filename.to_ascii_lowercase().ends_with(".tex") {
        return Err("Export filename must end with .tex.".to_string());
    }
    if filename.contains('/') || filename.contains('\\') {
        return Err("Export filename must not contain path separators.".to_string());
    }
    if std::path::Path::new(filename).components().count() != 1 {
        return Err("Export filename must be a filename, not a path.".to_string());
    }

    Ok(filename.to_string())
}

fn unique_workspace_path(workspace: &std::path::Path, filename: &str) -> std::path::PathBuf {
    let candidate = workspace.join(filename);
    if !candidate.exists() {
        return candidate;
    }

    let path = std::path::Path::new(filename);
    let stem = path
        .file_stem()
        .and_then(|value| value.to_str())
        .unwrap_or("untitled-note");

    for suffix in 2.. {
        let candidate = workspace.join(format!("{stem}-{suffix}.tex"));
        if !candidate.exists() {
            return candidate;
        }
    }

    unreachable!("unbounded suffix search should always return a candidate path")
}

fn main() {
    let mut context = tauri::generate_context!();
    context.set_default_window_icon(None);

    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            write_tex_note_file,
            export_tex_note_to_workspace
        ])
        .run(context)
        .expect("error while running tauri application");
}
