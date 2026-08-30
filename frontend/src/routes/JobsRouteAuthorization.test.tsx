import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useJobs } from "../hooks/useJobs";
import { JobsRoute } from "./JobsRoute";

let permissions = new Set<string>();

vi.mock("../auth", () => ({
  useAuth: () => ({ activeCompany: { branches: [] } }),
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../hooks/useJobs", () => ({
  useJobs: vi.fn(() => ({ isLoading: false, isError: false })),
}));
vi.mock("../components/jobs/CreateJobPanel", () => ({
  CreateJobPanel: () => <div>Create Job panel</div>,
}));

const renderRoute = () => render(<MemoryRouter><JobsRoute /></MemoryRouter>);

describe("JobsRoute authorization", () => {
  beforeEach(() => {
    permissions = new Set();
    vi.clearAllMocks();
  });

  it("disables the Job query without read authority", () => {
    renderRoute();
    expect(screen.getByText(/not authorized to view Jobs/i)).toBeVisible();
    expect(useJobs).toHaveBeenCalledWith(expect.any(Object), false);
  });

  it("does not expose creation to a read-only user", () => {
    permissions = new Set(["COMPANY_JOB_READ"]);
    renderRoute();
    expect(screen.getByRole("heading", { name: "Jobs" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Create Job" })).not.toBeInTheDocument();
    expect(useJobs).toHaveBeenCalledWith(expect.any(Object), true);
  });

  it("exposes creation only with Job manage authority", () => {
    permissions = new Set(["COMPANY_JOB_READ", "COMPANY_JOB_MANAGE"]);
    renderRoute();
    expect(screen.getByRole("button", { name: "Create Job" })).toBeVisible();
  });
});
