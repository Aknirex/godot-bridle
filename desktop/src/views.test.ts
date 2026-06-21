import { describe, expect, it } from "vitest";

import { appendJobEvent, renderKnowledgeAnswer, showError } from "./views";

describe("job event view", () => {
  it("renders text safely and updates progress", () => {
    const events = document.createElement("div");
    const progress = document.createElement("i");
    appendJobEvent(events, progress, {
      sequence: 3,
      stage: "download",
      message: "<unsafe>",
      progress: 0.5,
    });
    expect(events.textContent).toBe("03download<unsafe>");
    expect(events.querySelector("script")).toBeNull();
    expect(progress.style.width).toBe("50%");
  });

  it("renders Error messages", () => {
    const target = document.createElement("div");
    showError(target, new Error("failed"));
    expect(target.textContent).toBe("failed");
  });

  it("renders import diagnosis suggestions and citations safely", () => {
    const events = document.createElement("div");
    appendJobEvent(events, document.createElement("i"), {
      sequence: 8,
      type: "knowledge.diagnosis.completed",
      message: "Diagnosis complete",
      payload: {
        suggestion: "Check <script>mesh</script> [S1]",
        citations: [{ citation: "res://logs/import.log:1-2", score: 0.91 }],
      },
    });

    expect(events.textContent).toContain("Check <script>mesh</script> [S1]");
    expect(events.textContent).toContain("res://logs/import.log:1-2 · 0.910");
    expect(events.querySelector("script")).toBeNull();
  });
});

describe("knowledge answer view", () => {
  it("renders answer metadata, citations, and warnings", () => {
    const target = document.createElement("div");
    renderKnowledgeAnswer(target, {
      answer: "Movement speed is 10. [S1]",
      latency_ms: 42,
      citations: [{ citation: "res://player.gd:1-2", score: 0.8754 }],
      warnings: ["Index may be stale."],
    });

    expect(target.textContent).toContain("Movement speed is 10. [S1]");
    expect(target.textContent).toContain("42 ms");
    expect(target.textContent).toContain("res://player.gd:1-2 · 0.875");
    expect(target.textContent).toContain("Index may be stale.");
  });
});
