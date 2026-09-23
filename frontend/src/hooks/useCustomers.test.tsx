import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import * as customerApi from "../api/customers";
import {
  useCustomerCleanMajorityAdmission,
  useCustomerMutations,
  useCustomerPopulationRefresh,
} from "./useCustomers";

vi.mock("../api/customers", async (original) => ({
  ...await original<typeof import("../api/customers")>(),
  addCustomerNote: vi.fn().mockResolvedValue({ id: "note-1" }),
  admitCustomerCleanMajority: vi.fn(),
  recordCustomerConsent: vi.fn().mockResolvedValue({ id: "consent-1" }),
  refreshCustomerPopulation: vi.fn(),
}));
vi.mock("../auth", () => ({
  useAuth: () => ({
    activeCompany: {
      id: "company-1",
      default_branch_id: "branch-1",
      branches: [{ id: "branch-1" }],
    },
  }),
}));

describe("useCustomerMutations activity consistency", () => {
  it("admits the deterministic HCP majority and refreshes native rosters", async () => {
    const admit = vi.mocked(customerApi.admitCustomerCleanMajority);
    admit.mockResolvedValue({
      classification: "CUSTOMER_CLEAN_MAJORITY_ADMITTED",
      source_system: "housecall_pro",
      selected: 2,
      admitted: 1,
      replayed: 0,
      quarantined: 1,
      remaining_unexplained: 0,
      before_evidence_digest: "a".repeat(64),
      after_evidence_digest: "b".repeat(64),
      customer_admission_performed: true,
    });
    const client = new QueryClient({
      defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useCustomerCleanMajorityAdmission(), {
      wrapper,
    });

    act(() => result.current.mutate());
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(admit).toHaveBeenCalledWith("branch-1");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["customers"] });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ["administration", "migration-readiness"],
    });
  });

  it("reuses one command identity when the operator retries an uncertain refresh", async () => {
    const refresh = vi.mocked(customerApi.refreshCustomerPopulation);
    refresh
      .mockRejectedValueOnce(new Error("response lost"))
      .mockResolvedValueOnce({
        classification: "CUSTOMER_POPULATION_RECONCILED",
        run_id: "run-1",
        receipt_id: "receipt-1",
        replay: "replayed",
        source_system: "housecall_pro",
        counts: { total: 1, bound: 0, held: 0, ambiguous: 0, unexplained: 1 },
        evidence_digest: "a".repeat(64),
        completed_at: "2026-09-17T22:00:00Z",
        customer_admission_performed: false,
      });
    const client = new QueryClient({
      defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useCustomerPopulationRefresh(), { wrapper });

    act(() => result.current.mutate());
    await waitFor(() => expect(result.current.isError).toBe(true));
    act(() => result.current.mutate());
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(refresh).toHaveBeenCalledTimes(2);
    expect(refresh.mock.calls[0]?.[0]).toMatch(/^customer-population-refresh-.+/);
    expect(refresh.mock.calls[1]?.[0]).toBe(refresh.mock.calls[0]?.[0]);
    expect(refresh).toHaveBeenNthCalledWith(1, expect.any(String), "branch-1");
    expect(refresh).toHaveBeenNthCalledWith(2, expect.any(String), "branch-1");
  });

  it("invalidates detail, roster, and paginated timeline after a Customer event", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useCustomerMutations("customer-1"), { wrapper });
    act(() => result.current.addNote.mutate("Synthetic note"));
    await waitFor(() => expect(customerApi.addCustomerNote).toHaveBeenCalledWith("customer-1", "Synthetic note"));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["customer-timeline", "customer-1"] }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["customers"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["customer", "customer-1"] });
  });

  it("refreshes consent state and Customer history after recording consent", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useCustomerMutations("customer-1"), { wrapper });
    const input = { channel: "email", decision: "granted", source: "office", reason: "Synthetic acceptance" } as const;
    act(() => result.current.recordConsent.mutate(input));
    await waitFor(() => expect(customerApi.recordCustomerConsent).toHaveBeenCalledWith("customer-1", input));
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["customer-timeline", "customer-1"] }));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["customer-consents", "customer-1"] });
  });
});
