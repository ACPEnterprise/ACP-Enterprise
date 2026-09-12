import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import * as auth from "../auth";
import * as jobHooks from "../hooks/useJobs";
import { JobsRoute } from "./JobsRoute";

vi.mock("../auth");
vi.mock("../hooks/useJobs");

describe("JobsRoute Customer context", () => {
  it("filters the paginated Job workspace to the Customer selected on Customer detail", () => {
    vi.mocked(auth.useHasPermission).mockImplementation((permission) => permission === "COMPANY_JOB_READ");
    vi.mocked(auth.useAuth).mockReturnValue({ activeCompany: { branches: [] } } as never);
    vi.mocked(jobHooks.useJobs).mockReturnValue({ data: { items: [], page: 1, page_size: 20, total_count: 0, total_pages: 0 }, isLoading: false, isError: false } as never);
    render(<MemoryRouter initialEntries={["/jobs?customerId=customer-1"]}><JobsRoute /></MemoryRouter>);
    expect(jobHooks.useJobs).toHaveBeenCalledWith(expect.objectContaining({ customerId: "customer-1" }), true);
    expect(screen.getByRole("link", { name: "Return to Customer" })).toHaveAttribute("href", "/customers/customer-1");
  });
});
