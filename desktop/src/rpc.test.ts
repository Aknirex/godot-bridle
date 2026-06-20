import { describe, expect, it, vi } from "vitest";

import { RpcClient } from "./rpc";

describe("RpcClient", () => {
  it("matches sidecar responses to requests", async () => {
    const invoke = vi.fn().mockResolvedValue(undefined);
    const client = new RpcClient(invoke, vi.fn());

    const response = client.request("health");
    client.handle({ id: 1, result: { status: "ok" } });

    await expect(response).resolves.toEqual({ status: "ok" });
    expect(invoke).toHaveBeenCalledWith("sidecar_request", {
      request: { jsonrpc: "2.0", id: 1, method: "health", params: {} },
    });
  });

  it("forwards job events", () => {
    const handler = vi.fn();
    const client = new RpcClient(vi.fn(), handler);
    client.handle({ method: "job.event", params: { event: { sequence: 2 } } });
    expect(handler).toHaveBeenCalledWith({ sequence: 2 });
  });
});
