import { describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { FACTORY_CONTROL_OVERVIEW_PATH, getFactoryControlOverview } from "./factoryControl";

vi.mock("./client", () => ({ apiClient: { get: vi.fn() } }));

describe("Factory Control API", () => {
  it("uses the dedicated read-only platform overview endpoint", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { roadmap_digest: "a".repeat(64) } });
    await getFactoryControlOverview();
    expect(apiClient.get).toHaveBeenCalledWith(FACTORY_CONTROL_OVERVIEW_PATH);
  });
});
