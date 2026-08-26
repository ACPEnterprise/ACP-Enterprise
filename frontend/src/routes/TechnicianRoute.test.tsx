import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useTechnicianItinerary } from "../hooks/useTechnicianItinerary";
import { TechnicianRoute } from "./TechnicianRoute";

vi.mock("../hooks/useTechnicianItinerary", () => ({ useTechnicianItinerary: vi.fn() }));

describe("TechnicianRoute", () => {
  beforeEach(() => {
    vi.mocked(useTechnicianItinerary).mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        service_date: "2026-08-26",
        technician_display_name: "Alex Rivera",
        items: [
          {
            appointment_id: "appointment-1",
            appointment_number: "APT-1001",
            job_id: "job-1",
            job_number: "JOB-1001",
            customer_display_name: "Taylor Home",
            service_location_label: "10 Main Street, Springfield",
            window_start_at: "2026-08-26T13:00:00Z",
            window_end_at: "2026-08-26T15:00:00Z",
            assignment_status: "acknowledged",
            arrival_state: "en_route",
          },
        ],
      },
    } as never);
  });

  it("renders the assigned itinerary with mobile-reachable job context", () => {
    Object.defineProperty(window, "innerWidth", { value: 390, configurable: true });
    render(<MemoryRouter><TechnicianRoute /></MemoryRouter>);

    expect(screen.getByRole("heading", { name: "My day" })).toBeInTheDocument();
    expect(screen.getByLabelText("Service date")).toBeInTheDocument();
    expect(screen.getByText("Taylor Home")).toBeInTheDocument();
    expect(screen.getByText("En route")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open JOB-1001" })).toHaveAttribute("href", "/jobs/job-1");
  });

  it("renders a truthful empty state", () => {
    vi.mocked(useTechnicianItinerary).mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: { service_date: "2026-08-26", technician_display_name: "Alex Rivera", items: [] },
    } as never);
    render(<MemoryRouter><TechnicianRoute /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "No assigned visits" })).toBeInTheDocument();
  });
});
