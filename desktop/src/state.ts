export type AppState = { activeJob: string; projectPath: string };

export const appState: AppState = { activeJob: "", projectPath: "" };

export function activateJob(state: AppState, jobId: string): AppState {
  state.activeJob = jobId;
  return state;
}

export function selectProject(state: AppState, projectPath: string): AppState {
  state.projectPath = projectPath;
  return state;
}
