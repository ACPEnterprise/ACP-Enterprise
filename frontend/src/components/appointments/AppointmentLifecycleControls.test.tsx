import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useSchedulingMutations } from "../../hooks/useScheduling";
import type { AppointmentDetail } from "../../types/scheduling";
import { AppointmentLifecycleControls } from "./AppointmentLifecycleControls";

vi.mock("../../hooks/useScheduling");
const appointment = { id: "appointment-1", concurrency_version: 4, arrival_window_start_at: "2026-08-30T14:00:00Z", arrival_window_end_at: "2026-08-30T16:00:00Z", expected_duration_minutes: 90, capacity_units: "1.00" } as AppointmentDetail;
const controls = () => ({ cancel: { mutate: vi.fn(), isPending: false, error: null }, reschedule: { mutate: vi.fn(), isPending: false, error: null } });

describe("AppointmentLifecycleControls", () => {
  it("binds cancellation to the observed Appointment version", () => {
    const mutations = controls(); vi.mocked(useSchedulingMutations).mockReturnValue(mutations as never);
    render(<AppointmentLifecycleControls appointment={appointment} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel Appointment" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm cancel" }));
    expect(mutations.cancel.mutate).toHaveBeenCalledWith({ id: "appointment-1", input: { expected_version: 4, reason_code: "customer_request" } });
  });

  it("uses authoritative reschedule inputs rather than local calendar state", () => {
    const mutations = controls(); vi.mocked(useSchedulingMutations).mockReturnValue(mutations as never);
    render(<AppointmentLifecycleControls appointment={appointment} />);
    fireEvent.click(screen.getByRole("button", { name: "Reschedule" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm reschedule" }));
    expect(mutations.reschedule.mutate).toHaveBeenCalledWith(expect.objectContaining({ id: "appointment-1", input: expect.objectContaining({ expected_version: 4, expected_duration_minutes: 90, capacity_units: "1.00" }) }));
  });
});
