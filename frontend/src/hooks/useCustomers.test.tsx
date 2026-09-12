import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import * as customerApi from "../api/customers";
import { useCustomerMutations } from "./useCustomers";

vi.mock("../api/customers", async (original) => ({
  ...await original<typeof import("../api/customers")>(),
  addCustomerNote: vi.fn().mockResolvedValue({ id: "note-1" }),
  recordCustomerConsent: vi.fn().mockResolvedValue({ id: "consent-1" }),
}));

describe("useCustomerMutations activity consistency", () => {
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
