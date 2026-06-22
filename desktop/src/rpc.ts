export type Json = Record<string, unknown>;
export type RpcMessage = {
  id?: number;
  result?: unknown;
  error?: Json;
  method?: string;
  params?: Json;
};

export type Invoke = (command: string, args: Json) => Promise<unknown>;
type EventHandler = (event: Json) => void;

export async function waitForSidecar(
  invoke: Invoke,
  timeoutMs = 30_000,
  intervalMs = 250,
  onProgress: (elapsedMs: number) => void = () => undefined,
): Promise<void> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (await invoke("sidecar_status", {}) === true) return;
    onProgress(Date.now() - started);
    await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
  }
  throw new Error(
    `Local service did not become ready within ${Math.ceil(timeoutMs / 1_000)} seconds.`,
  );
}

export class RpcClient {
  private requestId = 0;
  private readonly pending = new Map<
    number,
    { resolve: (value: unknown) => void; reject: (reason: Error) => void }
  >();

  constructor(
    private readonly invoke: Invoke,
    private readonly eventHandler: EventHandler,
  ) {}

  request(method: string, params: Json = {}): Promise<unknown> {
    const id = ++this.requestId;
    const response = new Promise((resolve, reject) =>
      this.pending.set(id, { resolve, reject }),
    );
    void this.invoke("sidecar_request", {
      request: { jsonrpc: "2.0", id, method, params },
    }).catch((error: unknown) => {
      const waiter = this.pending.get(id);
      if (!waiter) return;
      this.pending.delete(id);
      const message = error instanceof Error ? error.message : String(error);
      waiter.reject(new Error(message));
    });
    return response;
  }

  handle(message: RpcMessage): void {
    if (message.id !== undefined) {
      const waiter = this.pending.get(message.id);
      if (!waiter) return;
      this.pending.delete(message.id);
      if (message.error) {
        waiter.reject(new Error(String(message.error.message ?? "Sidecar request failed")));
      } else {
        waiter.resolve(message.result);
      }
      return;
    }
    if (message.method === "job.event") {
      this.eventHandler(message.params?.event as Json);
    }
  }
}
