import { describe, expect, it } from "vitest";

import { activateJob, selectProject, type AppState } from "./state";

describe("application state", () => {
  it("tracks the selected project and active job independently", () => {
    const state: AppState = { activeJob: "", projectPath: "" };

    selectProject(state, "/game");
    activateJob(state, "job_123");

    expect(state).toEqual({ activeJob: "job_123", projectPath: "/game" });
  });
});
