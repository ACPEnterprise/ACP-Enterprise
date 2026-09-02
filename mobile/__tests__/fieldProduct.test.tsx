import { createFieldService, fieldIdempotencyKey } from "../src/api/fieldService";
import type { ApiClient } from "../src/api/client";
import { capabilitiesFromPermissions } from "../src/permissions/capabilities";
import { act, render, screen, waitFor } from "@testing-library/react-native";
import { JobsScreen } from "../src/screens/JobsScreen";
import { ApiFailure } from "../src/api/types";

describe("permission-driven field product contracts", () => {
  it("derives field surfaces from effective permissions, never role labels", () => {
    expect(capabilitiesFromPermissions(["COMPANY_JOB_READ", "COMPANY_JOB_EXECUTE", "COMPANY_ASSET_READ"])).toEqual(["home.view", "jobs.view", "jobs.execute", "assets.view"]);
    expect(capabilitiesFromPermissions(["TECHNICIAN", "COMPANY_ADMINISTRATOR"])).toEqual(["home.view"]);
  });

  it("uses only server-scoped itinerary and technician state reads", async () => {
    const request = jest.fn().mockResolvedValue({ service_date: "2026-09-01", technician_display_name: "Synthetic", items: [] });
    const service = createFieldService({ request } as unknown as ApiClient);
    await service.itinerary("2026-09-01");
    expect(request.mock.calls[0]?.[0]).toBe("/api/v1/technician/itinerary?service_date=2026-09-01");
    expect(request.mock.calls[0]?.[0]).not.toContain("employee_id");
  });

  it("sends authoritative versions and opaque idempotency for arrival", async () => {
    const request = jest.fn().mockResolvedValue({ version: 8, arrival_state: "en_route", status: "assigned" });
    const service = createFieldService({ request } as unknown as ApiClient);
    const key = fieldIdempotencyKey("en_route");
    await service.arrival("30000000-0000-4000-8000-000000000001", "en_route", 7, key);
    const options = request.mock.calls[0]?.[2] as RequestInit;
    expect(JSON.parse(String(options.body))).toEqual({ state: "en_route", expected_version: 7, idempotency_key: key });
    expect(key).toMatch(/^mobile-field:en_route:/);
  });

  it("never supplies Employee, Customer, Branch, communication, or payment authority in mutations", async () => {
    const request = jest.fn().mockResolvedValue({ id: "40000000-0000-4000-8000-000000000001", status: "in_progress", concurrency_version: 3 });
    const service = createFieldService({ request } as unknown as ApiClient);
    await service.transition("40000000-0000-4000-8000-000000000001", "start", 2);
    const body = JSON.parse(String((request.mock.calls[0]?.[2] as RequestInit).body));
    expect(body).toEqual({ expected_version: 2 });
    expect(JSON.stringify(body)).not.toMatch(/employee|customer|branch|phone|email|payment/i);
  });

  it("bounds the Job list to three assignment-scoped itinerary days", async () => {
    const itinerary = jest.fn(async (date: string) => ({ service_date: date, technician_display_name: "Synthetic", items: [] }));
    const service = { itinerary, state: jest.fn(), arrival: jest.fn(), transition: jest.fn(), workSummary: jest.fn(), customerDisposition: jest.fn(), note: jest.fn(), approval: jest.fn(), refreshHandoff: jest.fn() };
    const network = { isConnected: jest.fn(async () => true), subscribe: jest.fn(() => () => undefined) };
    render(<JobsScreen service={service} network={network} />);
    await waitFor(() => expect(itinerary).toHaveBeenCalledTimes(3));
    expect(screen.getByText(/assigned work only/i)).toBeOnTheScreen();
    expect(screen.getByText(/Completed history is unavailable/i)).toBeOnTheScreen();
  });

  it("uses assignment-scoped successor projections without client identity scope", async () => {
    const request = jest.fn()
      .mockResolvedValueOnce({ job_id: "40000000-0000-4000-8000-000000000001", history_limit: 10, attachment_upload_state: "source_required", items: [] })
      .mockResolvedValueOnce({ job_id: "40000000-0000-4000-8000-000000000001", available: false, estimate_number: null, estimate_status: null, acceptance_status: null, revision_number: null, revision_status: null, proposal_title: null, customer_message: null, total_amount: null, currency: null, expires_at: null, lines: [], customer_handoff_state: "server_authority_required" })
      .mockResolvedValueOnce({ days: 30, limit: 20, items: [] });
    const service = createFieldService({ request } as unknown as ApiClient);
    const job = "40000000-0000-4000-8000-000000000001";
    await service.equipment!(job); await service.estimate!(job); await service.history!();
    expect(request.mock.calls.map((call) => call[0])).toEqual([
      `/api/v1/technician/jobs/${job}/equipment`,
      `/api/v1/technician/jobs/${job}/estimate`,
      "/api/v1/technician/history?days=30&limit=20",
    ]);
    expect(JSON.stringify(request.mock.calls)).not.toMatch(/employee_id|customer_id|branch_id/i);
  });

  it("removes cached Job data when refreshed authority is revoked", async () => {
    const item = { appointment_id: "30000000-0000-4000-8000-000000000001", appointment_number: "APT-1", job_id: "40000000-0000-4000-8000-000000000001", job_number: "JOB-1", job_status: "ready", job_version: 1, customer_display_name: "Synthetic Customer", service_location_label: "Synthetic Site", window_start_at: "2026-09-02T12:00:00Z", window_end_at: "2026-09-02T13:00:00Z", assignment_status: "assigned", assignment_version: 1, arrival_state: "pending" as const, field_execution_enabled: true };
    let denied = false; let reconnect: ((connected: boolean) => void) | undefined;
    let itineraryCall = 0;
    const service = { itinerary: jest.fn(async (date: string) => { if (denied) throw new ApiFailure("forbidden", "Permission changed"); itineraryCall += 1; return { service_date: date, technician_display_name: "Synthetic", items: itineraryCall % 3 === 1 ? [item] : [] }; }), state: jest.fn(), arrival: jest.fn(), transition: jest.fn(), workSummary: jest.fn(), customerDisposition: jest.fn(), note: jest.fn(), approval: jest.fn(), refreshHandoff: jest.fn() };
    const network = { isConnected: jest.fn(async () => true), subscribe: jest.fn((listener: (connected: boolean) => void) => { reconnect = listener; return () => undefined; }) };
    render(<JobsScreen service={service} network={network} />);
    expect(await screen.findByText("Job JOB-1")).toBeOnTheScreen();
    denied = true; await act(async () => reconnect?.(true));
    await waitFor(() => expect(screen.queryByText("Job JOB-1")).not.toBeOnTheScreen());
  });
});
