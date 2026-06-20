import { describe, expect, it } from "vitest";

import { appendJobEvent, showError } from "./views";

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
});
