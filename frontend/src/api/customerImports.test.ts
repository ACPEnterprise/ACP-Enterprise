import { beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "./client";
import { admitCustomerImport, stageCustomerImport } from "./customerImports";

vi.mock("./client", () => ({
  activeCompanyId: vi.fn(),
  apiClient: { post: vi.fn() },
}));

describe("customer import API", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(client.activeCompanyId).mockReturnValue("company-1");
  });

  it("uploads a file through the tenant-scoped staging contract", async () => {
    vi.mocked(client.apiClient.post).mockResolvedValue({
      data: {
        batch_id: "batch-1",
        status: "staged",
        source_rows: 2,
        ready: 2,
        duplicates: 0,
        held: 0,
        rejected: 0,
        reused: false,
        source_sha256: "a".repeat(64),
        mapping_sha256: "b".repeat(64),
        file_format: "csv",
      },
    } as never);

    const file = new File(["ID,Name\ncus-1,One"], "customers.csv", { type: "text/csv" });
    await stageCustomerImport(file, "preview-key", {
      provider: "file",
      namespace: "file",
      mapping: { source_record_id: "ID", display_name: "Name" },
      branchId: "branch-1",
    });

    const [path, body, config] = vi.mocked(client.apiClient.post).mock.calls[0] ?? [];
    expect(path).toBe("/api/v1/customer-import/batches");
    expect(body).toBeInstanceOf(ArrayBuffer);
    expect(config).toMatchObject({
      timeout: 300_000,
      headers: {
        "Idempotency-Key": "preview-key",
        "X-Customer-Import-Provider": "file",
        "X-Customer-Import-Namespace": "file",
        "X-Branch-ID": "branch-1",
      },
    });
  });

  it("keeps admission on the same tenant-scoped batch", async () => {
    vi.mocked(client.apiClient.post).mockResolvedValue({
      data: {
        batch_id: "batch-1",
        status: "completed",
        created: 1,
        matched: 1,
        replayed: 0,
        held: 1,
        rejected: 0,
        processed: 3,
      },
    } as never);

    const result = await admitCustomerImport("batch-1", "company-1", "branch-1");
    expect(result.created + result.matched).toBe(2);
    expect(client.apiClient.post).toHaveBeenCalledWith(
      "/api/v1/customer-import/batches/batch-1/admit?limit=10000",
      {},
      expect.objectContaining({
        timeout: 1_800_000,
        headers: { "Content-Type": "application/json", "X-Branch-ID": "branch-1" },
      }),
    );
  });

  it("fails closed when the active company changes before admission", async () => {
    vi.mocked(client.activeCompanyId).mockReturnValue("company-2");

    await expect(admitCustomerImport("batch-1", "company-1")).rejects.toThrow(
      "active company changed",
    );
    expect(client.apiClient.post).not.toHaveBeenCalled();
  });
});
