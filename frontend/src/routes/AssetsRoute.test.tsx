import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AssetsRoute } from "./AssetsRoute";

let permissions = new Set<string>();
vi.mock("../auth", () => ({
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../api/assets", () => ({
  listAssets: vi.fn().mockResolvedValue([
    {
      id: "asset-1",
      company_id: "company-1",
      branch_id: "branch-1",
      asset_number: "AST-000001",
      asset_class: "vehicle",
      display_name: "Synthetic service vehicle",
      lifecycle: "active",
      predecessor_asset_id: null,
      provenance: { source: "synthetic" },
      identity_digest: "digest",
      version: 1,
      created_at: "2026-09-01T12:00:00Z",
      updated_at: "2026-09-01T12:00:00Z",
    },
  ]),
  getAsset: vi.fn(),
  listAssetActions: vi.fn().mockResolvedValue([]),
  createAsset: vi.fn(),
  recordAssetEvidence: vi.fn(),
  relateAsset: vi.fn(),
  recordAssetAction: vi.fn(),
}));

const show = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AssetsRoute />
    </QueryClientProvider>,
  );

describe("AssetsRoute authorization", () => {
  beforeEach(() => (permissions = new Set()));

  it("fails closed without Asset read authority", () => {
    show();
    expect(screen.getByText(/not authorized/)).toBeVisible();
  });

  it("keeps evidence visible but hides mutations for read-only users", async () => {
    permissions = new Set(["COMPANY_ASSET_READ"]);
    show();
    expect(await screen.findByText(/Synthetic service vehicle/)).toBeVisible();
    expect(screen.getByText(/Read-only access/)).toBeVisible();
    expect(screen.queryByText("Register Asset")).not.toBeInTheDocument();
  });

  it("exposes registration only with explicit Asset manage authority", async () => {
    permissions = new Set(["COMPANY_ASSET_READ", "COMPANY_ASSET_MANAGE"]);
    show();
    expect(
      await screen.findByRole("heading", { name: "Register Asset" }),
    ).toBeVisible();
    expect(screen.getByLabelText("Asset class")).toBeVisible();
  });
});
