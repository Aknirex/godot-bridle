use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager, State};

struct SidecarState {
    child: Mutex<Child>,
    stdin: Mutex<ChildStdin>,
}

#[tauri::command]
fn sidecar_request(
    request: serde_json::Value,
    state: State<'_, SidecarState>,
) -> Result<(), String> {
    let mut stdin = state
        .stdin
        .lock()
        .map_err(|_| "Sidecar input lock failed")?;
    serde_json::to_writer(&mut *stdin, &request).map_err(|error| error.to_string())?;
    stdin.write_all(b"\n").map_err(|error| error.to_string())?;
    stdin.flush().map_err(|error| error.to_string())
}

fn start_sidecar(app: &AppHandle) -> Result<SidecarState, String> {
    let state_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Cannot locate application data directory: {error}"))?;
    std::fs::create_dir_all(&state_dir)
        .map_err(|error| format!("Cannot create application data directory: {error}"))?;
    let database = state_dir.join("sidecar.sqlite3");
    let mut command = if cfg!(debug_assertions) {
        let project_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(|path| path.parent())
            .ok_or("Cannot locate project root")?;
        let mut command = Command::new("uv");
        command
            .args(["run", "bridle", "sidecar"])
            .current_dir(project_root);
        command
    } else {
        let executable = std::env::current_exe()
            .map_err(|error| format!("Cannot locate desktop executable: {error}"))?;
        let sidecar = executable
            .parent()
            .ok_or("Cannot locate desktop executable directory")?
            .join("bridle-sidecar");
        Command::new(sidecar)
    };
    command.arg("--db").arg(database);
    let mut child = command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|error| format!("Failed to start Bridle sidecar: {error}"))?;
    let stdin = child.stdin.take().ok_or("Sidecar stdin is unavailable")?;
    let stdout = child.stdout.take().ok_or("Sidecar stdout is unavailable")?;
    let handle = app.clone();
    std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            if let Ok(message) = serde_json::from_str::<serde_json::Value>(&line) {
                let _ = handle.emit("sidecar-message", message);
            }
        }
    });
    Ok(SidecarState {
        child: Mutex::new(child),
        stdin: Mutex::new(stdin),
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let state = start_sidecar(app.handle()).map_err(std::io::Error::other)?;
            app.manage(state);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![sidecar_request])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.try_state::<SidecarState>() {
                    if let Ok(mut child) = state.child.lock() {
                        let _ = child.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Godot Bridle");
}
