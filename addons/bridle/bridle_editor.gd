@tool
extends EditorPlugin

const POLL_INTERVAL_SECONDS := 1.0

var _dock: VBoxContainer
var _endpoint: LineEdit
var _token: LineEdit
var _prompt: TextEdit
var _status: Label
var _http: HTTPRequest
var _poll_timer: Timer
var _request_id := 0
var _pending_methods: Dictionary = {}
var _active_job_id := ""


func _enter_tree() -> void:
	_dock = VBoxContainer.new()
	_dock.name = "Bridle"
	_endpoint = _line_edit("Daemon endpoint", OS.get_environment("BRIDLE_DAEMON_ENDPOINT"))
	_token = _line_edit("Daemon token", OS.get_environment("BRIDLE_DAEMON_TOKEN"))
	_token.secret = true
	_prompt = TextEdit.new()
	_prompt.placeholder_text = "Describe a character to generate"
	_prompt.custom_minimum_size = Vector2(280, 120)
	_status = Label.new()
	_status.text = "Disconnected"
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_http = HTTPRequest.new()
	_http.timeout = 35.0
	_http.request_completed.connect(_on_request_completed)
	_poll_timer = Timer.new()
	_poll_timer.wait_time = POLL_INTERVAL_SECONDS
	_poll_timer.timeout.connect(_poll_job)
	_dock.add_child(_endpoint)
	_dock.add_child(_token)
	_dock.add_child(_prompt)
	_dock.add_child(_button("Connect", _connect_daemon))
	_dock.add_child(_button("Generate character", _generate_character))
	_dock.add_child(_status)
	_dock.add_child(_http)
	_dock.add_child(_poll_timer)
	add_control_to_dock(DOCK_SLOT_RIGHT_UL, _dock)


func _exit_tree() -> void:
	if is_instance_valid(_dock):
		remove_control_from_docks(_dock)
		_dock.queue_free()


func _line_edit(placeholder: String, value: String) -> LineEdit:
	var field := LineEdit.new()
	field.placeholder_text = placeholder
	field.text = value
	return field


func _button(label: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = label
	button.pressed.connect(callback)
	return button


func _connect_daemon() -> void:
	_send_rpc(&"system.health", {})


func _generate_character() -> void:
	var project_path := ProjectSettings.globalize_path("res://")
	var text := _prompt.text.strip_edges()
	if text.is_empty():
		_status.text = "Enter a character description first."
		return
	_send_rpc(
		&"workflows.submit",
		{
			"workflow_id": "character_gen",
			"project_path": project_path,
			"prompt": text,
			"provider_id": "meshy",
			"enable_pbr": true
		}
	)


func _send_rpc(method: StringName, params: Dictionary) -> void:
	if _endpoint.text.strip_edges().is_empty() or _token.text.is_empty():
		_status.text = "Set the daemon endpoint and token."
		return
	if _http.get_http_client_status() != HTTPClient.STATUS_DISCONNECTED:
		_status.text = "A Bridle request is already in progress."
		return
	_request_id += 1
	_pending_methods[_request_id] = method
	var headers := PackedStringArray([
		"Authorization: Bearer %s" % _token.text,
		"Content-Type: application/json"
	])
	var body := JSON.stringify({
		"jsonrpc": "2.0",
		"id": _request_id,
		"method": method,
		"params": params
	})
	var error := _http.request(
		_endpoint.text.trim_suffix("/") + "/rpc",
		headers,
		HTTPClient.METHOD_POST,
		body
	)
	if error != OK:
		_pending_methods.erase(_request_id)
		_status.text = "Could not start Bridle request: %s" % error_string(error)


func _on_request_completed(
	result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray
) -> void:
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	if result != HTTPRequest.RESULT_SUCCESS or response_code < 200 or response_code >= 300:
		_status.text = "Bridle request failed: HTTP %d / result %d" % [response_code, result]
		return
	if not parsed is Dictionary:
		_status.text = "Bridle returned invalid JSON."
		return
	var response: Dictionary = parsed
	var response_id: int = int(response.get("id", 0))
	var method: StringName = _pending_methods.get(response_id, &"")
	_pending_methods.erase(response_id)
	if response.has("error"):
		_status.text = str(response.error.get("message", "Bridle request failed"))
		return
	var value: Variant = response.get("result", {})
	match method:
		&"system.health":
			_status.text = "Connected to Bridle %s" % value.get("protocol_version", "")
		&"workflows.submit":
			_active_job_id = str(value.get("job_id", ""))
			_status.text = "Submitted %s" % _active_job_id
			if not _active_job_id.is_empty():
				_poll_timer.start()
		&"jobs.get":
			_update_job(value)


func _poll_job() -> void:
	if _active_job_id.is_empty():
		_poll_timer.stop()
		return
	_send_rpc(&"jobs.get", {"job_id": _active_job_id})


func _update_job(value: Dictionary) -> void:
	var state := str(value.get("state", "unknown"))
	var progress := float(value.get("progress", 0.0))
	_status.text = "%s — %d%%" % [state, roundi(progress * 100.0)]
	if state in ["succeeded", "failed", "cancelled"]:
		_poll_timer.stop()
		_active_job_id = ""
		if state == "succeeded":
			get_editor_interface().get_resource_filesystem().scan()
