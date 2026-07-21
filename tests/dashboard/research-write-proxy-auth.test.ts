import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { proxyResearch } from "../../src/lib/research-api/proxy";

describe("Research write proxy authentication", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    process.env.PRIVATE_PAPER_API_URL = "http://research-api.internal:8080";
    process.env.RESEARCH_WRITE_API_KEY = "dashboard-research-key";
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ status: "created" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    delete process.env.PRIVATE_PAPER_API_URL;
    delete process.env.RESEARCH_WRITE_API_KEY;
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("sends the backend credential on Research POSTs", async () => {
    await proxyResearch("/api/v1/research/experiments", {
      method: "POST",
      body: {},
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[1]?.headers).toMatchObject({
      "X-API-Key": "dashboard-research-key",
    });
  });

  it("does not send the backend credential on Research GETs", async () => {
    await proxyResearch("/api/v1/research/experiments");

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[1]?.headers).not.toHaveProperty(
      "X-API-Key",
    );
  });

  it("fails closed before forwarding a POST when the key is missing", async () => {
    delete process.env.RESEARCH_WRITE_API_KEY;

    const response = await proxyResearch("/api/v1/research/experiments", {
      method: "POST",
      body: {},
    });

    expect(response.status).toBe(502);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
