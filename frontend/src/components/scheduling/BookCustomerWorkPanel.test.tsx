import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCustomerDetail, useCustomerList } from "../../hooks/useCustomers";
import { useCreateServiceRequest } from "../../hooks/useOperations";
import { BookCustomerWorkPanel } from "./BookCustomerWorkPanel";

const mutate = vi.hoisted(() => vi.fn());
vi.mock("../../auth", () => ({
  useAuth: () => ({ activeCompany: { default_branch_id: "branch-1", branches: [{ id: "branch-1", name: "Main" }] } }),
}));
vi.mock("../../hooks/useCustomers");
vi.mock("../../hooks/useOperations");

describe("BookCustomerWorkPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useCustomerList).mockReturnValue({
      data: { items: [{ id: "customer-1", first_name: "Alex", last_name: "County", business_name: null }] },
      isError: false,
    } as never);
    vi.mocked(useCustomerDetail).mockImplementation((id) => ({
      data: id ? { properties: [{ id: "location-1", address_line_1: "10 Main St", city: "Albany" }] } : undefined,
      isLoading: false,
    }) as never);
    vi.mocked(useCreateServiceRequest).mockReturnValue({
      mutate,
      isPending: false,
      error: null,
      data: null,
    } as never);
  });

  it("requires a separate human confirmation before atomic Appointment and Job booking", async () => {
    render(<MemoryRouter><BookCustomerWorkPanel onClose={vi.fn()} /></MemoryRouter>);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /Customer/ }), "customer-1");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /Service Location/ }), "location-1");
    await userEvent.type(screen.getByRole("textbox", { name: "Customer-reported problem" }), "No cooling");
    await userEvent.click(screen.getByRole("button", { name: "Review booking" }));
    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Book this customer work?" })).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Confirm booking" }));
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        branch_id: "branch-1",
        customer_id: "customer-1",
        service_location_id: "location-1",
        customer_reported_problem: "No cooling",
      }),
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("truthfully keeps technician assignment separate after persistence", () => {
    vi.mocked(useCreateServiceRequest).mockReturnValue({
      mutate,
      isPending: false,
      error: null,
      data: {
        appointment: { id: "appointment-1", appointment_number: "APT-1" },
        job: { id: "job-1", job_number: "JOB-1" },
      },
    } as never);
    render(<MemoryRouter><BookCustomerWorkPanel onClose={vi.fn()} /></MemoryRouter>);
    expect(screen.getByText(/Assignment remains a separate human-confirmed Dispatch action/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Appointment" })).toHaveAttribute("href", "/appointments/appointment-1");
    expect(screen.getByRole("link", { name: "Open Job" })).toHaveAttribute("href", "/jobs/job-1");
    expect(screen.getByRole("link", { name: "Assign in Dispatch" })).toHaveAttribute("href", "/dispatch");
  });
});
