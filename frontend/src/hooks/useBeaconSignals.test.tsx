import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import * as beaconApi from "../api/beacon";
import type { BeaconSignal } from "../api/beacon";
import { useBeaconLifecycleActions } from "./useBeaconSignals";

vi.mock("../api/beacon", async (importOriginal) => {
  const original = await importOriginal<typeof beaconApi>();
  return { ...original, recordBeaconLifecycleAction: vi.fn() };
});

describe("useBeaconLifecycleActions", () => {
  it("refreshes the queue only after the backend accepts the event", async () => {
    let accept: (value: never) => void = () => undefined;
    const request = new Promise<never>((resolve) => {
      accept = resolve;
    });
    vi.mocked(beaconApi.recordBeaconLifecycleAction).mockReturnValue(request);
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useBeaconLifecycleActions(), { wrapper });

    act(() => {
      result.current.mutate({
        signal: {
          id: "signal-id",
          evidence_digest: "a".repeat(64),
        } as BeaconSignal,
        action: "acknowledge",
      });
    });
    expect(invalidate).not.toHaveBeenCalled();

    act(() => accept({ id: "event-id" } as never));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["beacon-signals"] });
  });
});
