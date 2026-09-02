import { createFieldService, fieldIdempotencyKey } from "../src/api/fieldService";
import type { ApiClient } from "../src/api/client";
import { capabilitiesFromPermissions } from "../src/permissions/capabilities";
import { render, screen, waitFor } from "@testing-library/react-native";
import { JobsScreen } from "../src/screens/JobsScreen";

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
    const service = { itinerary, state: jest.fn(), arrival: jest.fn(), transition: jest.fn(), workSummary: jest.fn(), customerDisposition: jest.fn() };
    const network = { isConnected: jest.fn(async () => true), subscribe: jest.fn(() => () => undefined) };
    render(<JobsScreen service={service} network={network} />);
    await waitFor(() => expect(itinerary).toHaveBeenCalledTimes(3));
    expect(screen.getByText(/assigned work only/i)).toBeOnTheScreen();
    expect(screen.getByText(/Source required.*completed history/i)).toBeOnTheScreen();
  });
});
