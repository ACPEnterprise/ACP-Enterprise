import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useCreateJobFromAppointment } from "../../hooks/useJobs";
import type { AppointmentDetail } from "../../types/scheduling";
import { CreateJobFromAppointmentPanel } from "./CreateJobFromAppointmentPanel";

vi.mock("../../hooks/useJobs");
const mutate = vi.fn();
const appointment = { id: "appointment-1", appointment_number: "APT-000001" } as AppointmentDetail;

describe("CreateJobFromAppointmentPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useCreateJobFromAppointment).mockReturnValue({ mutate, isPending: false, error: null } as never);
  });
  it("submits only Job metadata while preserving the authoritative source Appointment", async () => {
    render(<MemoryRouter><CreateJobFromAppointmentPanel appointment={appointment} onCancel={vi.fn()} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Create Job from APT-000001" })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Priority" }), "urgent");
    await userEvent.type(screen.getByRole("textbox", { name: "Customer-reported problem" }), "No cooling");
    await userEvent.click(screen.getByRole("button", { name: "Create Job" }));
    expect(mutate).toHaveBeenCalledWith(expect.objectContaining({ priority: "urgent", customer_reported_problem: "No cooling" }), expect.objectContaining({ onSuccess: expect.any(Function) }));
    expect(useCreateJobFromAppointment).toHaveBeenCalledWith("appointment-1");
  });
  it("prevents duplicate submission while pending", () => {
    vi.mocked(useCreateJobFromAppointment).mockReturnValue({ mutate, isPending: true, error: null } as never);
    render(<MemoryRouter><CreateJobFromAppointmentPanel appointment={appointment} onCancel={vi.fn()} /></MemoryRouter>);
    expect(screen.getByRole("button", { name: /Create Job/ })).toBeDisabled();
  });
});
