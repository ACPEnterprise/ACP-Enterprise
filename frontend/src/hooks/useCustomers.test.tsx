import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import * as customerApi from "../api/customers";
import { useCustomerMutations } from "./useCustomers";

vi.mock("../api/customers", async (original) => ({
  ...await original<typeof import("../api/customers")>(),
  addCustomerNote: vi.fn().mockResolvedValue({ id: "note-1" }),
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
});
