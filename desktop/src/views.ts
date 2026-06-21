import type { Json } from "./rpc";

export function appendJobEvent(container: HTMLElement, progress: HTMLElement, event: Json): void {
  const row = document.createElement("div");
  const time = document.createElement("time");
  const stage = document.createElement("b");
  const message = document.createElement("span");
  time.textContent = String(event.sequence).padStart(2, "0");
  stage.textContent = String(event.stage ?? event.type ?? "event");
  message.textContent = String(event.message ?? "");
  row.append(time, stage, message);
  container.append(row);
  const value = typeof event.progress === "number" ? event.progress * 100 : 0;
  progress.style.width = `${value}%`;
  if (event.type === "knowledge.diagnosis.completed") {
    container.append(renderDiagnosis(event.payload));
  }
}

export function showError(target: HTMLElement, error: unknown): void {
  target.textContent = error instanceof Error ? error.message : String(error);
}

export function renderKnowledgeAnswer(container: HTMLElement, raw: unknown): void {
  container.replaceChildren();
  const answer = asRecord(raw);
  const summary = document.createElement("p");
  summary.className = "answer-text";
  summary.textContent = String(answer.answer ?? "No answer returned.");
  container.append(summary);

  const meta = document.createElement("p");
  meta.className = "answer-meta";
  meta.textContent = `${Number(answer.latency_ms ?? 0)} ms`;
  container.append(meta);

  const citations = Array.isArray(answer.citations) ? answer.citations : [];
  if (citations.length) {
    const list = document.createElement("ol");
    list.className = "citations";
    citations.forEach((rawCitation) => list.append(renderCitation(rawCitation)));
    container.append(list);
  }

  const warnings = Array.isArray(answer.warnings) ? answer.warnings : [];
  warnings.forEach((warning) => {
    const row = document.createElement("p");
    row.className = "warning";
    row.textContent = String(warning);
    container.append(row);
  });
}

function renderDiagnosis(raw: unknown): HTMLElement {
  const payload = asRecord(raw);
  const panel = document.createElement("section");
  panel.className = "diagnosis";
  const heading = document.createElement("strong");
  heading.textContent = "Import diagnosis";
  const suggestion = document.createElement("p");
  suggestion.textContent = String(payload.suggestion ?? "No suggestion returned.");
  panel.append(heading, suggestion);
  const citations = Array.isArray(payload.citations) ? payload.citations : [];
  if (citations.length) {
    const list = document.createElement("ol");
    list.className = "citations";
    citations.forEach((citation) => list.append(renderCitation(citation)));
    panel.append(list);
  }
  return panel;
}

function renderCitation(raw: unknown): HTMLLIElement {
  const citation = asRecord(raw);
  const item = document.createElement("li");
  const location = document.createElement("code");
  location.textContent = String(citation.citation ?? citation.source_id ?? "unknown source");
  const score = typeof citation.score === "number" ? ` · ${citation.score.toFixed(3)}` : "";
  item.append(location, document.createTextNode(score));
  return item;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? value as Record<string, unknown> : {};
}
