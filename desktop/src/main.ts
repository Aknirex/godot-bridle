import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-dialog";
import { RpcClient, type Json, type RpcMessage } from "./rpc";
import { activateJob, appState, selectProject } from "./state";
import { appendJobEvent, renderKnowledgeAnswer, showError } from "./views";
import "./style.css";

const client = new RpcClient(invoke, (event) => {
  appendJobEvent($("#events"), $("#progress"), event);
  if (event.type === "knowledge.index.completed") {
    $("#knowledge-status").textContent = "Index complete.";
  }
});

void listen<RpcMessage>("sidecar-message", ({ payload }) => {
  client.handle(payload);
});

async function rpc(method: string, params: Json = {}): Promise<unknown> {
  return client.request(method, params);
}

document.querySelector<HTMLDivElement>("#app")!.innerHTML = `
  <aside>
    <div class="brand">BRIDLE <span>alpha</span></div>
    <nav>
      <button class="tab active" data-page="project">Project</button>
      <button class="tab" data-page="providers">Providers</button>
      <button class="tab" data-page="generate">Generate</button>
      <button class="tab" data-page="knowledge">Knowledge</button>
      <button class="tab" data-page="jobs">Jobs</button>
    </nav>
    <div id="connection">Connecting…</div>
  </aside>
  <main>
    <section id="project" class="page active">
      <p class="eyebrow">Workspace</p><h1>Open a Godot project</h1>
      <label>Project directory<div class="field-row"><input id="project-path" placeholder="/path/to/godot/project" /><button id="browse-project">Browse</button></div></label>
      <button id="open-project" class="primary">Open project</button>
      <pre id="project-result">No project selected.</pre>
    </section>
    <section id="providers" class="page">
      <p class="eyebrow">Connections</p><h1>Provider health</h1>
      <div id="provider-list" class="cards"></div>
      <div class="provider-editor">
        <h2>Provider configuration</h2>
        <p>Only the environment variable name is stored. API key values stay outside Bridle.</p>
        <div class="provider-grid">
          <label>Provider ID<input id="provider-id" placeholder="claude_custom" /></label>
          <label>Kind<select id="provider-kind"><option value="llm">LLM</option><option value="asset">Asset</option><option value="gateway">Gateway</option></select></label>
          <label>Backend<input id="provider-backend" value="litellm" /></label>
          <label>Model<input id="provider-model" placeholder="provider/model-name" /></label>
          <label>Base URL (optional)<input id="provider-base-url" placeholder="https://…" /></label>
          <label>API key environment variable<input id="provider-api-key-env" placeholder="PROVIDER_API_KEY" /></label>
          <label>Capabilities<input id="provider-capabilities" placeholder="llm.chat, llm.stream" /></label>
          <label>Default for<input id="provider-default-for" placeholder="llm.chat" /></label>
        </div>
        <button id="save-provider" class="primary">Save provider metadata</button>
        <output id="provider-save-result"></output>
      </div>
    </section>
    <section id="generate" class="page">
      <p class="eyebrow">Text to 3D</p><h1>Generate a character</h1>
      <label>Description<textarea id="prompt" rows="7" placeholder="A low-poly knight with a blue cloak"></textarea></label>
      <label>Provider<select id="provider"><option value="meshy_mock">Meshy Mock</option></select></label>
      <label class="check"><input id="enhance-prompt" type="checkbox" /> Enhance prompt with DeepSeek</label>
      <label>Godot executable (optional)<input id="godot-path" placeholder="/path/to/godot" /></label>
      <button id="generate-button" class="primary">Start generation</button>
      <p id="generate-result"></p>
    </section>
    <section id="jobs" class="page">
      <p class="eyebrow">Execution</p><h1>Job monitor</h1>
      <div class="jobbar"><strong id="job-id">No active job</strong><button id="cancel-job">Cancel</button></div>
      <div class="progress"><i id="progress"></i></div>
      <div id="events" class="events"></div>
    </section>
    <section id="knowledge" class="page">
      <p class="eyebrow">Project context</p><h1>Knowledge &amp; Assistant</h1>
      <div class="knowledge-actions">
        <button id="index-knowledge" class="primary">Index project</button>
        <span id="knowledge-status">Not indexed in this session.</span>
      </div>
      <label>Question<textarea id="knowledge-question" rows="5" placeholder="How is player movement implemented?"></textarea></label>
      <div class="field-row knowledge-query-options">
        <label>Results<input id="knowledge-top-k" type="number" min="1" max="20" value="5" /></label>
        <button id="ask-knowledge" class="primary">Ask project</button>
      </div>
      <div id="knowledge-answer" class="answer-panel">Index the project, then ask a question.</div>
    </section>
  </main>`;

const $ = <T extends HTMLElement>(selector: string) => document.querySelector<T>(selector)!;
const projectPath = $("#project-path") as HTMLInputElement;

document.querySelectorAll<HTMLButtonElement>(".tab").forEach((tab) => {
  tab.onclick = () => {
    document.querySelectorAll(".tab,.page").forEach((node) => node.classList.remove("active"));
    tab.classList.add("active");
    $(`#${tab.dataset.page}`).classList.add("active");
  };
});

$("#open-project").onclick = async () => {
  try {
    const result = await rpc("open_project", { path: projectPath.value });
    selectProject(appState, projectPath.value);
    $("#project-result").textContent = JSON.stringify(result, null, 2);
    await refreshKnowledgeStatus();
  } catch (error) { showError($("#project-result"), error); }
};

$("#browse-project").onclick = async () => {
  const selected = await open({ directory: true, multiple: false });
  if (selected) projectPath.value = selected;
};

$("#generate-button").onclick = async () => {
  const prompt = ($("#prompt") as HTMLTextAreaElement).value;
  const godot = ($("#godot-path") as HTMLInputElement).value;
  try {
    const result = await rpc("submit_workflow", {
      workflow_id: "character_gen", project_path: projectPath.value, prompt,
      provider_id: ($("#provider") as HTMLSelectElement).value,
      enhance_prompt: ($("#enhance-prompt") as HTMLInputElement).checked,
      ...(godot ? { godot_executable: godot } : {}),
    }) as { job_id: string };
    await monitorJob(result.job_id);
    $("#generate-result").textContent = `Submitted ${appState.activeJob}`;
    (document.querySelector('[data-page="jobs"]') as HTMLButtonElement).click();
  } catch (error) { showError($("#generate-result"), error); }
};

$("#index-knowledge").onclick = async () => {
  const status = $("#knowledge-status");
  try {
    const path = selectedProjectPath();
    status.textContent = "Submitting index job…";
    const result = await rpc("index_project_knowledge", { project_path: path }) as {
      job_id: string;
    };
    await monitorJob(result.job_id);
    status.textContent = `Indexing in ${result.job_id}…`;
  } catch (error) {
    showError(status, error);
  }
};

$("#ask-knowledge").onclick = async () => {
  const button = $("#ask-knowledge") as HTMLButtonElement;
  const target = $("#knowledge-answer");
  try {
    button.disabled = true;
    target.textContent = "Retrieving project evidence…";
    const result = await rpc("ask_project_knowledge", {
      project_path: selectedProjectPath(),
      question: ($("#knowledge-question") as HTMLTextAreaElement).value,
      top_k: Number(( $("#knowledge-top-k") as HTMLInputElement).value),
    });
    renderKnowledgeAnswer(target, result);
  } catch (error) {
    showError(target, error);
  } finally {
    button.disabled = false;
  }
};

$("#cancel-job").onclick = async () => {
  if (appState.activeJob) await rpc("cancel_job", { job_id: appState.activeJob });
};

$("#save-provider").onclick = async () => {
  const output = $("#provider-save-result");
  const value = (selector: string) => ($(selector) as HTMLInputElement).value.trim();
  try {
    const baseUrl = value("#provider-base-url");
    const model = value("#provider-model");
    const apiKeyEnv = value("#provider-api-key-env");
    const result = await rpc("save_provider_config", {
      provider_id: value("#provider-id"),
      kind: ($("#provider-kind") as HTMLSelectElement).value,
      backend: value("#provider-backend"),
      ...(model ? { model } : {}),
      ...(baseUrl ? { base_url: baseUrl } : {}),
      ...(apiKeyEnv ? { api_key_env: apiKeyEnv } : {}),
      capabilities: commaSeparated(value("#provider-capabilities")),
      default_for: commaSeparated(value("#provider-default-for")),
    });
    output.textContent = `Saved ${String((result as Json).provider_id)}.`;
    await refreshProviders();
  } catch (error) {
    showError(output, error);
  }
};

async function initialize() {
  try {
    const health = await rpc("health") as Json;
    $("#connection").textContent = `${health.name} ${health.version}`;
    await refreshProviders();
  } catch (error) { $("#connection").textContent = `Offline: ${error}`; }
}

async function monitorJob(jobId: string): Promise<void> {
  activateJob(appState, jobId);
  $("#job-id").textContent = appState.activeJob;
  $("#events").replaceChildren();
  await rpc("stream_job_events", { job_id: appState.activeJob, after_sequence: 0 });
}

function selectedProjectPath(): string {
  const path = appState.projectPath || projectPath.value;
  if (!path) throw new Error("Open a Godot project first.");
  return path;
}

async function refreshProviders(): Promise<void> {
  const providers = await rpc("list_providers") as Json[];
  const assetSelect = $("#provider") as HTMLSelectElement;
  assetSelect.replaceChildren();
  providers.filter((provider) => provider.kind === "asset").forEach((provider) => {
    const option = document.createElement("option");
    option.value = String(provider.provider_id);
    option.textContent = String(provider.provider_id);
    assetSelect.append(option);
  });

  const list = $("#provider-list");
  list.replaceChildren();
  providers.forEach((provider) => {
    const article = document.createElement("article");
    const heading = document.createElement("h3");
    heading.textContent = String(provider.provider_id);
    const details = document.createElement("p");
    details.textContent = [provider.backend, provider.model].filter(Boolean).join(" · ")
      || String(provider.kind);
    const test = document.createElement("button");
    test.textContent = "Test connection";
    const configure = document.createElement("button");
    configure.textContent = "Configure";
    const output = document.createElement("output");
    test.onclick = async () => {
      try {
        output.textContent = JSON.stringify(await rpc("test_provider", {
          provider_id: provider.provider_id,
        }));
      } catch (error) {
        output.textContent = error instanceof Error ? error.message : String(error);
      }
    };
    configure.onclick = () => populateProviderEditor(provider);
    article.append(heading, details, test, configure, output);
    list.append(article);
  });
}

function populateProviderEditor(provider: Json): void {
  const set = (selector: string, value: unknown) => {
    ($(selector) as HTMLInputElement).value = value == null ? "" : String(value);
  };
  set("#provider-id", provider.provider_id);
  ($("#provider-kind") as HTMLSelectElement).value = String(provider.kind);
  set("#provider-backend", provider.backend);
  set("#provider-model", provider.model);
  set("#provider-base-url", provider.base_url);
  set("#provider-api-key-env", provider.api_key_env);
  set("#provider-capabilities", Array.isArray(provider.capabilities)
    ? provider.capabilities.join(", ") : "");
  set("#provider-default-for", Array.isArray(provider.default_for)
    ? provider.default_for.join(", ") : "");
}

function commaSeparated(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

async function refreshKnowledgeStatus(): Promise<void> {
  const status = await rpc("get_project_knowledge_status", {
    project_path: selectedProjectPath(),
  }) as Json;
  $("#knowledge-status").textContent = status.indexed
    ? `${status.documents_indexed} documents · ${status.chunks_indexed} chunks`
    : "Project has not been indexed.";
}

initialize();
