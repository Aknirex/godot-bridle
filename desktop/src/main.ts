import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { open } from "@tauri-apps/plugin-dialog";
import { RpcClient, type Json, type RpcMessage } from "./rpc";
import { activateJob, appState } from "./state";
import { appendJobEvent, showError } from "./views";
import "./style.css";

const client = new RpcClient(invoke, (event) =>
  appendJobEvent($("#events"), $("#progress"), event),
);

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
    $("#project-result").textContent = JSON.stringify(result, null, 2);
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
    activateJob(appState, result.job_id);
    $("#job-id").textContent = appState.activeJob;
    $("#events").replaceChildren();
    await rpc("stream_job_events", { job_id: appState.activeJob, after_sequence: 0 });
    $("#generate-result").textContent = `Submitted ${appState.activeJob}`;
    (document.querySelector('[data-page="jobs"]') as HTMLButtonElement).click();
  } catch (error) { showError($("#generate-result"), error); }
};

$("#cancel-job").onclick = async () => {
  if (appState.activeJob) await rpc("cancel_job", { job_id: appState.activeJob });
};

async function initialize() {
  try {
    const health = await rpc("health") as Json;
    $("#connection").textContent = `${health.name} ${health.version}`;
    const providers = await rpc("list_providers") as Json[];
    const assetProviders = providers.filter((provider) => provider.kind === "asset");
    ($("#provider") as HTMLSelectElement).innerHTML = assetProviders
      .map((provider) => `<option value="${provider.provider_id}">${provider.provider_id}</option>`)
      .join("");
    $("#provider-list").innerHTML = providers.map((provider) => `
      <article><h3>${provider.provider_id}</h3><p>${provider.backend ?? provider.kind}</p>
      <button data-provider="${provider.provider_id}">Test connection</button><output></output></article>`).join("");
    document.querySelectorAll<HTMLButtonElement>("[data-provider]").forEach((button) => {
      button.onclick = async () => {
        const output = button.nextElementSibling!;
        try { output.textContent = JSON.stringify(await rpc("test_provider", { provider_id: button.dataset.provider })); }
        catch (error) { output.textContent = error instanceof Error ? error.message : String(error); }
      };
    });
  } catch (error) { $("#connection").textContent = `Offline: ${error}`; }
}

initialize();
