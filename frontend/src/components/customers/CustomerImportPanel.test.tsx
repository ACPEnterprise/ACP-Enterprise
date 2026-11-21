import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { activeCompanyId } from "../../api/client";
import { stageCustomerImport } from "../../api/customerImports";
import { useCustomerCleanMajorityAdmission, useCustomerPopulationRefresh } from "../../hooks/useCustomers";
import { CustomerImportPanel } from "./CustomerImportPanel";

vi.mock("../../api/client", () => ({ activeCompanyId: vi.fn() }));
vi.mock("../../api/customerImports", () => ({
  admitCustomerImport: vi.fn(),
  stageCustomerImport: vi.fn(),
}));
vi.mock("../../api/errors", () => ({
  getOperatorApiError: (_error: unknown, fallback: string) => ({
    title: fallback,
    message: "The operation could not be completed.",
  }),
}));
vi.mock("../../hooks/useCustomers", () => ({
  useCustomerCleanMajorityAdmission: vi.fn(),
  useCustomerPopulationRefresh: vi.fn(),
}));

const staged = (batchId: string) => ({
  batch_id: batchId,
  status: "staged" as const,
  source_rows: 1,
  ready: 1,
  duplicates: 0,
  held: 0,
  rejected: 0,
  reused: false,
  source_sha256: "a".repeat(64),
  mapping_sha256: "b".repeat(64),
  file_format: "csv" as const,
});

function renderPanel() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <CustomerImportPanel />
    </QueryClientProvider>,
  );
}

describe("CustomerImportPanel", () => {
  it("does not let an older validation response replace a newer file", async () => {
    vi.mocked(activeCompanyId).mockReturnValue("company-1");
    vi.mocked(useCustomerPopulationRefresh).mockReturnValue({
      mutate: vi.fn(), isPending: false, isError: false, error: null, data: undefined,
    } as never);
    vi.mocked(useCustomerCleanMajorityAdmission).mockReturnValue({
      mutate: vi.fn(), isPending: false, isError: false, error: null, data: undefined,
    } as never);

    let resolveFirst: ((value: ReturnType<typeof staged>) => void) | undefined;
    vi.mocked(stageCustomerImport)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
      .mockResolvedValueOnce(staged("batch-new"));

    renderPanel();
    const input = screen.getByLabelText("Choose file") as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(["ID,Name\ncus-old,Old"], "old.csv", { type: "text/csv" })] },
    });
    await screen.findByText("old.csv");

    fireEvent.change(input, {
      target: { files: [new File(["ID,Name\ncus-new,New"], "new.csv", { type: "text/csv" })] },
    });
    resolveFirst?.(staged("batch-old"));

    await waitFor(() => expect(screen.getByText("new.csv")).toBeInTheDocument());
    expect(screen.queryByText("old.csv")).not.toBeInTheDocument();
    expect(stageCustomerImport).toHaveBeenCalledTimes(2);
  });
});
