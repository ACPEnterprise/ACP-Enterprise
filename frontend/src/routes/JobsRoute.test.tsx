import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useJobs } from "../hooks/useJobs";
import { JobsRoute } from "./JobsRoute";

vi.mock("../hooks/useJobs");
vi.mock("../auth", () => ({
  useAuth: () => ({ activeCompany: { branches: [] } }),
  useHasPermission: () => true,
}));

describe("JobsRoute Customer context", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(useJobs).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total_count: 0, page: 1, page_size: 20, total_pages: 0 },
    } as never);
  });

  it("preserves the selected Customer as a server-side Job filter", () => {
    render(
      <MemoryRouter initialEntries={["/jobs?customerId=customer-1"]}>
        <JobsRoute />
      </MemoryRouter>,
    );

    expect(useJobs).toHaveBeenCalledWith(
      expect.objectContaining({ customerId: "customer-1", page: 1, pageSize: 20 }),
      true,
    );
    expect(screen.getByText(/Showing Jobs linked to the Customer selected/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Show all Jobs" })).toHaveAttribute("href", "/jobs");
  });
});
