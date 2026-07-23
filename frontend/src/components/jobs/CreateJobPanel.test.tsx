import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCustomerDetail, useCustomerList } from "../../hooks/useCustomers";
import { useCreateJob } from "../../hooks/useJobs";
import { CreateJobPanel } from "./CreateJobPanel";

vi.mock("../../auth", () => ({ useAuth: () => ({ activeCompany: { default_branch_id: "branch-1", branches: [{ id: "branch-1", name: "Main", code: "MAIN" }] } }) }));
vi.mock("../../hooks/useCustomers"); vi.mock("../../hooks/useJobs");
const mutate = vi.fn();

describe("CreateJobPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useCustomerList).mockReturnValue({ isLoading: false, isError: false, data: { items: [{ id: "customer-1", first_name: "Alex", last_name: "Taylor", business_name: null }], total: 1 } } as never);
    vi.mocked(useCustomerDetail).mockReturnValue({ isLoading: false, data: { properties: [{ id: "location-1", address_line_1: "10 Main Street", city: "Albany" }] } } as never);
    vi.mocked(useCreateJob).mockReturnValue({ mutate, isPending: false, error: null } as never);
  });
  it("requires authoritative references and submits the typed create request", async () => {
    render(<MemoryRouter><CreateJobPanel onCancel={vi.fn()} /></MemoryRouter>);
    const submit = screen.getByRole("button", { name: "Create Job" }); expect(submit).toBeDisabled();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /^Customer/ }), "customer-1");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /^Service Location/ }), "location-1");
    await userEvent.type(screen.getByLabelText("Customer-reported problem"), "No cooling");
    await userEvent.click(submit);
    expect(mutate).toHaveBeenCalledWith(expect.objectContaining({ branch_id: "branch-1", customer_id: "customer-1", service_location_id: "location-1", customer_reported_problem: "No cooling" }), expect.objectContaining({ onSuccess: expect.any(Function) }));
  });
  it("prevents duplicate submissions while creation is pending", () => {
    vi.mocked(useCreateJob).mockReturnValue({ mutate, isPending: true, error: null } as never);
    render(<MemoryRouter><CreateJobPanel onCancel={vi.fn()} /></MemoryRouter>);
    expect(screen.getByRole("button", { name: /Create Job/ })).toBeDisabled();
  });
});
