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
}

export function showError(target: HTMLElement, error: unknown): void {
  target.textContent = error instanceof Error ? error.message : String(error);
}
