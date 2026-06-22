import { describe, expect, it, vi } from "vitest";

import { RpcClient, waitForSidecar } from "./rpc";

describe("RpcClient", () => {
  it("matches sidecar responses to requests", async () => {
    const invoke = vi.fn().mockResolvedValue(undefined);
    const client = new RpcClient(invoke, vi.fn());

    const response = client.request("system.health");
    client.handle({ id: 1, result: { status: "ok" } });

    await expect(response).resolves.toEqual({ status: "ok" });
    expect(invoke).toHaveBeenCalledWith("sidecar_request", {
      request: { jsonrpc: "2.0", id: 1, method: "system.health", params: {} },
    });
  });

  it("forwards job events", () => {
    const handler = vi.fn();
    const client = new RpcClient(vi.fn(), handler);
    client.handle({ method: "job.event", params: { event: { sequence: 2 } } });
    expect(handler).toHaveBeenCalledWith({ sequence: 2 });
  });
});

describe("waitForSidecar", () => {
  it("polls until the sidecar reports ready", async () => {
    const invoke = vi.fn()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);

    await waitForSidecar(invoke, 1_000, 0);

    expect(invoke).toHaveBeenCalledTimes(2);
    expect(invoke).toHaveBeenCalledWith("sidecar_status", {});
  });

  it("rejects with a bounded startup error", async () => {
    const invoke = vi.fn().mockResolvedValue(false);

    await expect(waitForSidecar(invoke, 5, 1)).rejects.toThrow(
      "Local service did not become ready within 1 seconds.",
    );
  });
});
