use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const JSONRPC_VERSION: &str = "2.0";
pub const PROTOCOL_VERSION: &str = "2026-06-22";

pub fn canonical_method(method: &str) -> &str {
    match method {
        "health" => "system.health",
        "open_project" => "projects.open",
        "list_providers" => "providers.list",
        "save_provider_config" => "providers.save",
        "test_provider" => "providers.test",
        "submit_workflow" => "workflows.submit",
        "get_job_status" => "jobs.get",
        "cancel_job" => "jobs.cancel",
        "stream_job_events" => "jobs.subscribe",
        "index_project_knowledge" => "knowledge.index",
        "get_project_knowledge_status" => "knowledge.status",
        "query_project_knowledge" => "knowledge.query",
        "ask_project_knowledge" => "knowledge.ask",
        value => value,
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JsonRpcRequest {
    pub jsonrpc: String,
    #[serde(default)]
    pub id: Value,
    pub method: String,
    #[serde(default)]
    pub params: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiscoveryDocument {
    pub protocol_version: String,
    pub endpoint: String,
    pub token: String,
    pub pid: u32,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn legacy_methods_are_supported_for_one_protocol_version() {
        assert_eq!(canonical_method("health"), "system.health");
        assert_eq!(canonical_method("submit_workflow"), "workflows.submit");
        assert_eq!(canonical_method("jobs.get"), "jobs.get");
    }
}

pub fn capabilities() -> Vec<&'static str> {
    vec![
        "request_response",
        "job.event",
        "llm.stream",
        "mcp.streamable_http",
        "lazy_worker",
    ]
}
