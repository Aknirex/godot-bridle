export type AppState = { activeJob: string };

export const appState: AppState = { activeJob: "" };

export function activateJob(state: AppState, jobId: string): AppState {
  state.activeJob = jobId;
  return state;
}
