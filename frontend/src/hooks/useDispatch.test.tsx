import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import * as dispatchApi from "../api/dispatch";
import { appointmentKeys } from "./useScheduling";
import { dispatchKeys, useDispatchMutations } from "./useDispatch";

vi.mock("../api/dispatch");

describe("Dispatch and Calendar interoperability", () => {
  it("refreshes assignment and Calendar projections after canonical reassignment", async () => {
    vi.mocked(dispatchApi.assignPrimary).mockResolvedValue({
      id: "assignment-1",
    } as never);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const result = renderHook(() => useDispatchMutations(), { wrapper });

    result.result.current.assign.mutate({
      appointmentId: "appointment-1",
      employeeId: "michael-brian",
      reason: "Office reassignment",
      version: 2,
    });

    await waitFor(() => expect(result.result.current.assign.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: dispatchKeys.all });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: appointmentKeys.lists() });
  });
});
