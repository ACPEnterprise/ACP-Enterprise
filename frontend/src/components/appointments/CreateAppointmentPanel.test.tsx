import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useSchedulingMutations } from "../../hooks/useScheduling";
import { CreateAppointmentPanel } from "./CreateAppointmentPanel";
vi.mock("../../hooks/useScheduling");
describe("CreateAppointmentPanel", () => {
  it("submits a stable tenant-scoped Scheduling command shape", () => {
    const mutate = vi.fn(); vi.mocked(useSchedulingMutations).mockReturnValue({ create: { mutate, isPending: false, error: null } } as never);
    render(<CreateAppointmentPanel onClose={vi.fn()} />);
    for (const [label, value] of [["Branch ID", "branch-1"], ["Customer ID", "customer-1"], ["Service Location ID", "location-1"], ["Arrival window start", "2026-08-30T09:00"], ["Arrival window end", "2026-08-30T11:00"]]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Create authoritative Appointment" }));
    expect(mutate).toHaveBeenCalledWith(expect.objectContaining({ branch_id: "branch-1", customer_id: "customer-1", service_location_id: "location-1", expected_duration_minutes: 60, idempotency_key: expect.any(String) }), expect.any(Object));
  });
});
