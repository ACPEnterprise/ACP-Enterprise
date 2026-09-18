import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { FACTORY_CONTROL_OVERVIEW_PATH, getFactoryControlOverview } from "./factoryControl";

vi.mock("./client", () => ({ apiClient: { get: vi.fn() } }));

describe("factory control API", () => {
  beforeEach(() => vi.clearAllMocks());

  it("requests the private overview with optional lane and domain drilldown", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { authority_sha: "a".repeat(40) } });
    await getFactoryControlOverview({ lane: "OM1-A", domain: "release" });
    expect(apiClient.get).toHaveBeenCalledWith(FACTORY_CONTROL_OVERVIEW_PATH, {
      params: { lane: "OM1-A", domain: "release" },
    });
  });
});
