import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import axios from "axios";
import type { PropsWithChildren } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as mobileApi from "./api";
import { mobileEngineeringKeys, useMilestoneAction } from "./hooks";

vi.mock("./api", async (loadOriginal) => ({
  ...(await loadOriginal<typeof import("./api")>()),
  actOnMilestone: vi.fn(),
  listRoadmaps: vi.fn(),
}));

describe("useMilestoneAction stale-version recovery", () => {
  let queryClient: QueryClient;
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    queryClient.setQueryDefaults(mobileEngineeringKeys.roadmaps(), {
      queryFn: mobileApi.listRoadmaps,
    });
    queryClient.setQueryData(mobileEngineeringKeys.roadmaps(), { marker: "stale" });
  });

  it("refetches current roadmap data without retrying the owner action", async () => {
    vi.mocked(mobileApi.actOnMilestone).mockRejectedValueOnce(
      new axios.AxiosError(
        "conflict",
        "409",
        undefined,
        undefined,
        { status: 409, statusText: "Conflict", headers: {}, config: {} as never, data: { detail: "Milestone version is stale." } },
      ),
    );
    vi.mocked(mobileApi.listRoadmaps).mockResolvedValue({ marker: "fresh" } as never);
    const { result } = renderHook(() => useMilestoneAction(), { wrapper });

    act(() => result.current.mutate({ id: "milestone-1", version: 7, action: "start" }));

    await waitFor(() => expect(mobileApi.listRoadmaps).toHaveBeenCalledOnce());
    await waitFor(() => expect(result.current.isError).toBe(false));
    expect(mobileApi.actOnMilestone).toHaveBeenCalledOnce();
    expect(queryClient.getQueryData(mobileEngineeringKeys.roadmaps())).toEqual({ marker: "fresh" });
  });
});
