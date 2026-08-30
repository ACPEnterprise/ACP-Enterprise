import { fireEvent, render, screen } from "@testing-library/react";
import { AxiosError } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LuminaryRoute } from "./LuminaryRoute";

const state = vi.hoisted(() => ({
  canRead: true,
  canAnalyze: true,
  error: undefined as unknown,
  refetch: vi.fn(),
  analyze: vi.fn(),
}));

vi.mock("../auth", () => ({
  useHasPermission: (permission: string) => permission.endsWith("_READ") ? state.canRead : state.canAnalyze,
}));
vi.mock("../hooks/useLuminary", () => ({
  useLuminaryBriefing: () => ({ isPending: false, isError: Boolean(state.error), error: state.error, data: undefined, refetch: state.refetch }),
  useAnalyzeLuminary: () => ({ mutate: state.analyze, isPending: false, isError: false }),
}));

describe("Luminary workspace recovery", () => {
  beforeEach(() => {
    state.canRead = true;
    state.canAnalyze = true;
    state.error = undefined;
    state.refetch.mockReset();
    state.analyze.mockReset();
  });

  it("retries a temporary briefing failure without offering analysis", () => {
    state.error = new AxiosError("unavailable");
    render(<LuminaryRoute />);
    expect(screen.getByText(/No briefing state was inferred/i)).toBeVisible();
    expect(screen.queryByRole("button", { name: /Analyze accepted evidence/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Retry briefing/i }));
    expect(state.refetch).toHaveBeenCalledOnce();
  });

  it("offers analysis only for a concealed not-found briefing", () => {
    state.error = new AxiosError("missing", undefined, undefined, undefined, { status: 404 } as never);
    render(<LuminaryRoute />);
    fireEvent.click(screen.getByRole("button", { name: /Analyze accepted evidence/i }));
    expect(state.analyze).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: /Retry briefing/i })).toBeNull();
  });
});
