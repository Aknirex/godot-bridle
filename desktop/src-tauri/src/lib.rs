use command_group::{CommandGroup, GroupChild};
use futures_util::StreamExt;
use serde::Deserialize;
use serde_json::Value;
use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use tauri::{AppHandle, Emitter, Manager, State};

#[derive(Clone, Deserialize)]
struct DaemonConnection {
    endpoint: String,
    token: String,
}

struct DaemonInner {
    child: Mutex<Option<GroupChild>>,
    connection: Mutex<Option<DaemonConnection>>,
    ready: AtomicBool,
}

struct DaemonState {
    inner: Arc<DaemonInner>,
}

#[tauri::command]
fn sidecar_status(state: State<'_, DaemonState>) -> bool {
    state.inner.ready.load(Ordering::Acquire)
}

#[tauri::command]
async fn sidecar_request(
    request: Value,
    app: AppHandle,
    state: State<'_, DaemonState>,
) -> Result<(), String> {
    let connection = state
        .inner
        .connection
        .lock()
        .map_err(|_| "Daemon connection lock failed")?
        .clone()
        .ok_or("Bridle daemon is not ready")?;
    let response = reqwest::Client::new()
        .post(format!("{}/rpc", connection.endpoint))
        .bearer_auth(&connection.token)
        .json(&request)
        .send()
        .await
        .map_err(|error| format!("Daemon request failed: {error}"))?;
    if !response.status().is_success() {
        return Err(format!("Daemon returned HTTP {}", response.status()));
    }
    let message = response
        .json::<Value>()
        .await
        .map_err(|error| format!("Daemon response was invalid: {error}"))?;
    app.emit("sidecar-message", message)
        .map_err(|error| error.to_string())
}

fn start_daemon(app: AppHandle, inner: Arc<DaemonInner>) -> Result<(), String> {
    let state_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("Cannot locate application data directory: {error}"))?;
    std::fs::create_dir_all(&state_dir)
        .map_err(|error| format!("Cannot create application data directory: {error}"))?;
    let mut command = daemon_command(&app)?;
    command
        .arg("--state-dir")
        .arg(&state_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    let mut child = command
        .group_spawn()
        .map_err(|error| format!("Failed to start Bridle daemon: {error}"))?;
    let stdout = child
        .inner()
        .stdout
        .take()
        .ok_or("Daemon stdout is unavailable")?;
    let line = BufReader::new(stdout)
        .lines()
        .next()
        .ok_or("Daemon exited before ready")?
        .map_err(|error| format!("Cannot read daemon ready message: {error}"))?;
    let ready: Value = serde_json::from_str(&line)
        .map_err(|error| format!("Daemon ready message was invalid: {error}"))?;
    if ready.get("method").and_then(Value::as_str) != Some("daemon.ready") {
        return Err("Daemon did not emit daemon.ready".to_string());
    }
    let discovery_path = state_dir.join("daemon.json");
    let discovery = std::fs::read(&discovery_path)
        .map_err(|error| format!("Cannot read daemon discovery file: {error}"))?;
    let connection: DaemonConnection = serde_json::from_slice(&discovery)
        .map_err(|error| format!("Daemon discovery file was invalid: {error}"))?;
    *inner
        .connection
        .lock()
        .map_err(|_| "Daemon connection lock failed")? = Some(connection.clone());
    *inner.child.lock().map_err(|_| "Daemon child lock failed")? = Some(child);
    inner.ready.store(true, Ordering::Release);
    app.emit(
        "sidecar-message",
        serde_json::json!({
            "jsonrpc": "2.0",
            "method": "daemon.ready",
            "params": {"endpoint": connection.endpoint}
        }),
    )
    .map_err(|error| error.to_string())?;
    tauri::async_runtime::spawn(forward_events(app, connection));
    Ok(())
}

async fn forward_events(app: AppHandle, connection: DaemonConnection) {
    let response = reqwest::Client::new()
        .get(format!("{}/events", connection.endpoint))
        .bearer_auth(connection.token)
        .send()
        .await;
    let Ok(response) = response else {
        return;
    };
    let mut stream = response.bytes_stream();
    let mut buffer = String::new();
    while let Some(chunk) = stream.next().await {
        let Ok(chunk) = chunk else {
            break;
        };
        buffer.push_str(&String::from_utf8_lossy(&chunk));
        while let Some(index) = buffer.find("\n\n") {
            let event = buffer[..index].to_string();
            buffer.drain(..index + 2);
            let data = event
                .lines()
                .filter_map(|line| line.strip_prefix("data: "))
                .collect::<Vec<_>>()
                .join("\n");
            if let Ok(message) = serde_json::from_str::<Value>(&data) {
                let _ = app.emit("sidecar-message", message);
            }
        }
    }
}

fn daemon_command(app: &AppHandle) -> Result<Command, String> {
    if let Ok(executable) = std::env::var("BRIDLE_DAEMON") {
        return Ok(Command::new(executable));
    }
    if cfg!(debug_assertions) {
        let manifest_dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let executable = if cfg!(windows) {
            manifest_dir.join("target/debug/bridled.exe")
        } else {
            manifest_dir.join("target/debug/bridled")
        };
        if executable.is_file() {
            return Ok(Command::new(executable));
        }
        let project_root = manifest_dir
            .parent()
            .and_then(|path| path.parent())
            .ok_or("Cannot locate project root")?;
        let mut command = Command::new("cargo");
        command
            .args(["run", "--quiet", "--bin", "bridled", "--"])
            .current_dir(manifest_dir)
            .env("BRIDLE_PROJECT_ROOT", project_root);
        return Ok(command);
    }
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|error| format!("Cannot locate application resources: {error}"))?;
    let executable = if cfg!(windows) {
        resource_dir.join("bridle-daemon-runtime/bridled.exe")
    } else {
        resource_dir.join("bridle-daemon-runtime/bridled")
    };
    Ok(Command::new(executable))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let inner = Arc::new(DaemonInner {
        child: Mutex::new(None),
        connection: Mutex::new(None),
        ready: AtomicBool::new(false),
    });
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(DaemonState {
            inner: inner.clone(),
        })
        .setup(move |app| {
            let handle = app.handle().clone();
            let daemon = inner.clone();
            std::thread::spawn(move || {
                if let Err(error) = start_daemon(handle.clone(), daemon) {
                    let _ = handle.emit(
                        "sidecar-message",
                        serde_json::json!({
                            "jsonrpc": "2.0",
                            "method": "daemon.failed",
                            "params": {"safe_details": error}
                        }),
                    );
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![sidecar_request, sidecar_status])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.try_state::<DaemonState>() {
                    if let Ok(mut child) = state.inner.child.lock() {
                        if let Some(mut child) = child.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Godot Bridle");
}
