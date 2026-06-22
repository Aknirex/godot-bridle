use async_stream::stream;
use axum::extract::State;
use axum::http::{header, HeaderMap, StatusCode};
use axum::response::sse::{Event, KeepAlive, Sse};
use axum::response::IntoResponse;
use axum::routing::{get, post};
use axum::{Json, Router};
use bridle_protocol::{canonical_method, capabilities, DiscoveryDocument, PROTOCOL_VERSION};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::convert::Infallible;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, Command};
use tokio::sync::{broadcast, oneshot, Mutex};
use tokio::time::timeout;

const WORKER_READY_TIMEOUT: Duration = Duration::from_secs(5);
const REQUEST_TIMEOUT: Duration = Duration::from_secs(30);
const WORKER_IDLE_SECONDS: u64 = 60;

#[derive(Clone)]
struct AppState {
    token: Arc<String>,
    state_dir: Arc<PathBuf>,
    worker: Arc<Mutex<Option<WorkerClient>>>,
    events: broadcast::Sender<Value>,
    active_jobs: Arc<AtomicUsize>,
}

struct WorkerClient {
    child: Arc<Mutex<Child>>,
    stdin: Arc<Mutex<ChildStdin>>,
    pending: Arc<Mutex<HashMap<String, oneshot::Sender<Value>>>>,
    last_used: Arc<AtomicU64>,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let state_dir = parse_state_dir()?;
    std::fs::create_dir_all(&state_dir)?;
    let token = random_token();
    let (events, _) = broadcast::channel(512);
    let state = AppState {
        token: Arc::new(token.clone()),
        state_dir: Arc::new(state_dir.clone()),
        worker: Arc::new(Mutex::new(None)),
        events,
        active_jobs: Arc::new(AtomicUsize::new(0)),
    };
    let app = Router::new()
        .route("/health", get(health_handler))
        .route("/rpc", post(rpc_handler))
        .route("/events", get(events_handler))
        .route("/mcp", post(mcp_handler))
        .with_state(state.clone());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let discovery = DiscoveryDocument {
        protocol_version: PROTOCOL_VERSION.to_string(),
        endpoint: format!("http://{address}"),
        token,
        pid: std::process::id(),
    };
    write_discovery(&state_dir.join("daemon.json"), &discovery)?;
    println!(
        "{}",
        serde_json::to_string(&json!({
            "jsonrpc": "2.0",
            "method": "daemon.ready",
            "params": {
                "protocol_version": PROTOCOL_VERSION,
                "endpoint": discovery.endpoint,
            }
        }))?
    );
    tokio::spawn(idle_worker_monitor(state.clone()));
    axum::serve(listener, app).await?;
    Ok(())
}

async fn health_handler(State(state): State<AppState>, headers: HeaderMap) -> impl IntoResponse {
    if let Err(response) = authorize(&headers, &state) {
        return response;
    }
    Json(json!({
        "name": "godot-bridle-daemon",
        "version": env!("CARGO_PKG_VERSION"),
        "protocol_version": PROTOCOL_VERSION,
        "status": "ok",
        "worker_running": state.worker.lock().await.is_some(),
        "active_jobs": state.active_jobs.load(Ordering::Acquire),
    }))
    .into_response()
}

async fn rpc_handler(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(mut request): Json<Value>,
) -> impl IntoResponse {
    if let Err(response) = authorize(&headers, &state) {
        return response;
    }
    if !valid_origin(&headers) {
        return (StatusCode::FORBIDDEN, "Origin is not allowed").into_response();
    }
    let id = request.get("id").cloned().unwrap_or(Value::Null);
    let method = request
        .get("method")
        .and_then(Value::as_str)
        .map(canonical_method)
        .unwrap_or("")
        .to_string();
    if method.is_empty() {
        return Json(rpc_error(id, -32600, "Invalid request")).into_response();
    }
    request["method"] = Value::String(method.clone());
    if method == "system.health" {
        return Json(json!({
            "jsonrpc": "2.0",
            "id": id,
            "result": {
                "name": "godot-bridle",
                "status": "ok",
                "protocol_version": PROTOCOL_VERSION,
                "worker_running": state.worker.lock().await.is_some(),
            }
        }))
        .into_response();
    }
    if method == "system.capabilities" {
        return Json(json!({
            "jsonrpc": "2.0",
            "id": id,
            "result": {
                "protocol_version": PROTOCOL_VERSION,
                "capabilities": capabilities(),
            }
        }))
        .into_response();
    }
    match forward_to_worker(&state, request).await {
        Ok(response) => Json(response).into_response(),
        Err(message) => Json(rpc_error(id, -32010, &message)).into_response(),
    }
}

async fn events_handler(State(state): State<AppState>, headers: HeaderMap) -> impl IntoResponse {
    if let Err(response) = authorize(&headers, &state) {
        return response;
    }
    if !valid_origin(&headers) {
        return (StatusCode::FORBIDDEN, "Origin is not allowed").into_response();
    }
    let mut receiver = state.events.subscribe();
    let output = stream! {
        loop {
            match receiver.recv().await {
                Ok(value) => yield Ok::<Event, Infallible>(
                    Event::default().event("message").json_data(value).unwrap_or_else(|_| Event::default())
                ),
                Err(broadcast::error::RecvError::Lagged(_)) => continue,
                Err(broadcast::error::RecvError::Closed) => break,
            }
        }
    };
    Sse::new(output)
        .keep_alive(KeepAlive::new().interval(Duration::from_secs(15)))
        .into_response()
}

async fn mcp_handler(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(request): Json<Value>,
) -> impl IntoResponse {
    if let Err(response) = authorize(&headers, &state) {
        return response;
    }
    if !valid_origin(&headers) {
        return (StatusCode::FORBIDDEN, "Origin is not allowed").into_response();
    }
    let id = request.get("id").cloned().unwrap_or(Value::Null);
    let method = request
        .get("method")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    if method == "initialize" {
        return Json(json!({
            "jsonrpc": "2.0",
            "id": id,
            "result": {
                "protocolVersion": "2025-11-25",
                "capabilities": {"tools": {"listChanged": false}},
                "serverInfo": {"name": "godot-bridle", "version": env!("CARGO_PKG_VERSION")}
            }
        }))
        .into_response();
    }
    if method == "tools/list" {
        return Json(json!({
            "jsonrpc": "2.0",
            "id": id,
            "result": {"tools": mcp_tools()}
        }))
        .into_response();
    }
    if method == "tools/call" {
        let params = request.get("params").cloned().unwrap_or_else(|| json!({}));
        let name = params.get("name").and_then(Value::as_str).unwrap_or("");
        let arguments = params
            .get("arguments")
            .cloned()
            .unwrap_or_else(|| json!({}));
        let mapped = match name {
            "bridle_open_project" => "projects.open",
            "bridle_list_providers" => "providers.list",
            "bridle_submit_workflow" => "workflows.submit",
            "bridle_get_job" => "jobs.get",
            "bridle_cancel_job" => "jobs.cancel",
            _ => {
                return Json(rpc_error(id, -32602, "Unknown or unsafe MCP tool")).into_response();
            }
        };
        let worker_request = json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": mapped,
            "params": arguments,
        });
        return match forward_to_worker(&state, worker_request).await {
            Ok(response) => {
                let result = response.get("result").cloned().unwrap_or(Value::Null);
                Json(json!({
                    "jsonrpc": "2.0",
                    "id": id,
                    "result": {"content": [{"type": "text", "text": result.to_string()}]}
                }))
                .into_response()
            }
            Err(message) => Json(rpc_error(id, -32010, &message)).into_response(),
        };
    }
    Json(rpc_error(id, -32601, "Method not found")).into_response()
}

async fn forward_to_worker(state: &AppState, request: Value) -> Result<Value, String> {
    let mut guard = state.worker.lock().await;
    if guard.is_none() {
        *guard = Some(WorkerClient::spawn(state).await?);
    }
    let worker = guard.as_ref().expect("worker was initialized");
    let method = request
        .get("method")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let response = worker.request(request).await?;
    if method == "workflows.submit" && response.get("result").is_some() {
        state.active_jobs.fetch_add(1, Ordering::AcqRel);
    }
    Ok(response)
}

impl WorkerClient {
    async fn spawn(state: &AppState) -> Result<Self, String> {
        let mut command = worker_command(&state.state_dir);
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .kill_on_drop(true)
            .spawn()
            .map_err(|error| format!("Failed to spawn Python worker: {error}"))?;
        let stdin = child.stdin.take().ok_or("Worker stdin is unavailable")?;
        let stdout = child.stdout.take().ok_or("Worker stdout is unavailable")?;
        let mut lines = BufReader::new(stdout).lines();
        let ready = timeout(WORKER_READY_TIMEOUT, lines.next_line())
            .await
            .map_err(|_| "Python worker did not become ready within 5 seconds".to_string())?
            .map_err(|error| format!("Worker ready read failed: {error}"))?
            .ok_or("Python worker exited before ready")?;
        let ready_value: Value = serde_json::from_str(&ready)
            .map_err(|error| format!("Worker ready message was invalid: {error}"))?;
        if ready_value.get("method").and_then(Value::as_str) != Some("sidecar.ready") {
            return Err("Python worker did not emit sidecar.ready".to_string());
        }
        let pending: Arc<Mutex<HashMap<String, oneshot::Sender<Value>>>> =
            Arc::new(Mutex::new(HashMap::new()));
        let reader_pending = pending.clone();
        let event_sender = state.events.clone();
        let active_jobs = state.active_jobs.clone();
        tokio::spawn(async move {
            while let Ok(Some(line)) = lines.next_line().await {
                let Ok(message) = serde_json::from_str::<Value>(&line) else {
                    continue;
                };
                if let Some(id) = message.get("id") {
                    let key = id_key(id);
                    if let Some(sender) = reader_pending.lock().await.remove(&key) {
                        let _ = sender.send(message);
                    }
                    continue;
                }
                if is_terminal_job_event(&message) {
                    active_jobs
                        .fetch_update(Ordering::AcqRel, Ordering::Acquire, |value| {
                            Some(value.saturating_sub(1))
                        })
                        .ok();
                }
                let _ = event_sender.send(message);
            }
            let mut pending = reader_pending.lock().await;
            for (_, sender) in pending.drain() {
                let _ = sender.send(rpc_error(Value::Null, -32011, "Python worker exited"));
            }
        });
        Ok(Self {
            child: Arc::new(Mutex::new(child)),
            stdin: Arc::new(Mutex::new(stdin)),
            pending,
            last_used: Arc::new(AtomicU64::new(now_seconds())),
        })
    }

    async fn request(&self, request: Value) -> Result<Value, String> {
        let id = request.get("id").cloned().unwrap_or(Value::Null);
        let key = id_key(&id);
        let (sender, receiver) = oneshot::channel();
        self.pending.lock().await.insert(key.clone(), sender);
        let mut encoded = serde_json::to_vec(&request)
            .map_err(|error| format!("Cannot encode worker request: {error}"))?;
        encoded.push(b'\n');
        if let Err(error) = self.stdin.lock().await.write_all(&encoded).await {
            self.pending.lock().await.remove(&key);
            return Err(format!("Cannot write worker request: {error}"));
        }
        self.last_used.store(now_seconds(), Ordering::Release);
        timeout(REQUEST_TIMEOUT, receiver)
            .await
            .map_err(|_| "Python worker request timed out".to_string())?
            .map_err(|_| "Python worker response channel closed".to_string())
    }

    fn idle_seconds(&self) -> u64 {
        now_seconds().saturating_sub(self.last_used.load(Ordering::Acquire))
    }
}

async fn idle_worker_monitor(state: AppState) {
    let mut interval = tokio::time::interval(Duration::from_secs(5));
    loop {
        interval.tick().await;
        if state.active_jobs.load(Ordering::Acquire) > 0 {
            continue;
        }
        let mut guard = state.worker.lock().await;
        let should_reap = guard
            .as_ref()
            .is_some_and(|worker| worker.idle_seconds() >= WORKER_IDLE_SECONDS);
        if should_reap {
            if let Some(worker) = guard.take() {
                let _ = worker.child.lock().await.kill().await;
                let _ = state.events.send(json!({
                    "jsonrpc": "2.0",
                    "method": "worker.stopped",
                    "params": {"reason": "idle_timeout"}
                }));
            }
        }
    }
}

fn worker_command(state_dir: &Path) -> Command {
    let db = state_dir.join("sidecar.sqlite3");
    if let Ok(executable) = std::env::var("BRIDLE_WORKER") {
        let mut command = Command::new(executable);
        command.arg("--db").arg(db);
        return command;
    }
    if let Ok(current) = std::env::current_exe() {
        let name = if cfg!(windows) {
            "bridle-sidecar.exe"
        } else {
            "bridle-sidecar"
        };
        let parent = current.parent().unwrap_or_else(|| Path::new("."));
        for candidate in [
            current.with_file_name(name),
            parent.join("bridle-sidecar-runtime").join(name),
            parent
                .parent()
                .unwrap_or(parent)
                .join("bridle-sidecar-runtime")
                .join(name),
        ] {
            // A same-named executable can be a stale PyInstaller artifact. Only
            // trust workers produced by the current Nuitka packaging pipeline.
            let manifest = candidate
                .parent()
                .unwrap_or(parent)
                .join("bridle-worker.json");
            if candidate.is_file() && valid_worker_manifest(&manifest) {
                let mut command = Command::new(candidate);
                command.arg("--db").arg(db);
                return command;
            }
        }
    }
    let mut command = Command::new("uv");
    command.args(["run", "bridle", "sidecar", "--db"]).arg(db);
    command
}

fn valid_worker_manifest(path: &Path) -> bool {
    let Ok(contents) = std::fs::read_to_string(path) else {
        return false;
    };
    let Ok(value) = serde_json::from_str::<Value>(&contents) else {
        return false;
    };
    value.get("packager").and_then(Value::as_str) == Some("nuitka")
        && value.get("protocol_version").and_then(Value::as_str) == Some(PROTOCOL_VERSION)
}

fn authorize(headers: &HeaderMap, state: &AppState) -> Result<(), axum::response::Response> {
    let expected = format!("Bearer {}", state.token);
    if headers
        .get(header::AUTHORIZATION)
        .and_then(|value| value.to_str().ok())
        == Some(expected.as_str())
    {
        return Ok(());
    }
    Err((StatusCode::UNAUTHORIZED, "Invalid daemon token").into_response())
}

fn valid_origin(headers: &HeaderMap) -> bool {
    let Some(origin) = headers.get(header::ORIGIN) else {
        return true;
    };
    let Ok(origin) = origin.to_str() else {
        return false;
    };
    origin == "tauri://localhost"
        || origin == "http://tauri.localhost"
        || origin == "https://tauri.localhost"
        || origin.starts_with("vscode-webview://")
        || origin.starts_with("http://127.0.0.1:")
}

fn parse_state_dir() -> Result<PathBuf, String> {
    let mut args = std::env::args_os().skip(1);
    while let Some(argument) = args.next() {
        if argument == "--state-dir" {
            return args
                .next()
                .map(PathBuf::from)
                .ok_or_else(|| "--state-dir requires a path".to_string());
        }
    }
    if let Ok(value) = std::env::var("BRIDLE_STATE_DIR") {
        return Ok(PathBuf::from(value));
    }
    Ok(std::env::temp_dir().join("godot-bridle"))
}

fn write_discovery(path: &Path, discovery: &DiscoveryDocument) -> std::io::Result<()> {
    std::fs::write(path, serde_json::to_vec(discovery)?)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))?;
    }
    #[cfg(windows)]
    {
        let user = match (
            std::env::var("USERDOMAIN").ok(),
            std::env::var("USERNAME").ok(),
        ) {
            (Some(domain), Some(name)) => format!("{domain}\\{name}"),
            (_, Some(name)) => name,
            _ => {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::PermissionDenied,
                    "Cannot identify the current user for discovery ACL",
                ));
            }
        };
        let status = std::process::Command::new("icacls")
            .arg(path)
            .args(["/inheritance:r", "/grant:r", &format!("{user}:F")])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()?;
        if !status.success() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::PermissionDenied,
                "Failed to restrict discovery file ACL",
            ));
        }
    }
    Ok(())
}

fn random_token() -> String {
    let bytes: [u8; 32] = rand::random();
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn id_key(value: &Value) -> String {
    serde_json::to_string(value).unwrap_or_else(|_| "null".to_string())
}

fn now_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn rpc_error(id: Value, code: i64, message: &str) -> Value {
    json!({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})
}

fn is_terminal_job_event(message: &Value) -> bool {
    if message.get("method").and_then(Value::as_str) != Some("job.event") {
        return false;
    }
    matches!(
        message
            .pointer("/params/event/type")
            .and_then(Value::as_str),
        Some("job.succeeded" | "job.failed" | "job.cancelled")
    )
}

fn mcp_tools() -> Value {
    json!([
        {"name": "bridle_open_project", "description": "Open and inspect a Godot project", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
        {"name": "bridle_list_providers", "description": "List configured Bridle providers", "inputSchema": {"type": "object"}},
        {"name": "bridle_submit_workflow", "description": "Submit a Bridle background workflow", "inputSchema": {"type": "object"}},
        {"name": "bridle_get_job", "description": "Read a Bridle job status", "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}},
        {"name": "bridle_cancel_job", "description": "Request cancellation of a Bridle job", "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}}
    ])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn worker_manifest_rejects_stale_packagers_and_protocols() {
        let root = std::env::temp_dir().join(format!("bridled-test-{}", random_token()));
        std::fs::create_dir_all(&root).unwrap();
        let manifest = root.join("bridle-worker.json");
        std::fs::write(
            &manifest,
            json!({"packager": "pyinstaller", "protocol_version": PROTOCOL_VERSION}).to_string(),
        )
        .unwrap();
        assert!(!valid_worker_manifest(&manifest));
        std::fs::write(
            &manifest,
            json!({"packager": "nuitka", "protocol_version": "old"}).to_string(),
        )
        .unwrap();
        assert!(!valid_worker_manifest(&manifest));
        std::fs::write(
            &manifest,
            json!({"packager": "nuitka", "protocol_version": PROTOCOL_VERSION}).to_string(),
        )
        .unwrap();
        assert!(valid_worker_manifest(&manifest));
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn origin_policy_accepts_local_clients_only() {
        let mut headers = HeaderMap::new();
        headers.insert(header::ORIGIN, "tauri://localhost".parse().unwrap());
        assert!(valid_origin(&headers));
        headers.insert(
            header::ORIGIN,
            "vscode-webview://editor-123".parse().unwrap(),
        );
        assert!(valid_origin(&headers));
        headers.insert(header::ORIGIN, "https://attacker.example".parse().unwrap());
        assert!(!valid_origin(&headers));
    }

    #[test]
    fn token_has_full_256_bits_of_hex_storage() {
        let token = random_token();
        assert_eq!(token.len(), 64);
        assert!(token.bytes().all(|value| value.is_ascii_hexdigit()));
    }
}
