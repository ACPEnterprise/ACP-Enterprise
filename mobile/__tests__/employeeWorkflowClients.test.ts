import { ApiClient } from "../src/api/client";
import { createFieldService } from "../src/api/fieldService";
import { createPayrollService } from "../src/api/payroll";
import { capabilitiesFromPermissions } from "../src/permissions/capabilities";

describe("employee workflow clients", () => {
  const client = { request: jest.fn(), requestText: jest.fn() } as unknown as ApiClient;
  beforeEach(() => jest.clearAllMocks());

  it("uses only own Payroll endpoints and protected HTML retrieval", async () => {
    const payroll = createPayrollService(client);
    (client.request as jest.Mock).mockResolvedValueOnce([]).mockResolvedValueOnce({}); (client.requestText as jest.Mock).mockResolvedValue({ content: "safe", contentType: "text/html" });
    await payroll.statements(); await payroll.status(); await payroll.artifact("10000000-0000-4000-8000-000000000001");
    expect((client.request as jest.Mock).mock.calls.map((call) => call[0])).toEqual(["/api/v1/payroll/me/pay-statements", "/api/v1/payroll/me/payroll-status"]);
    expect(client.requestText).toHaveBeenCalledWith("/api/v1/payroll/me/pay-statements/10000000-0000-4000-8000-000000000001/artifact");
  });

  it("uses authoritative field contracts without employee identity or client time", async () => {
    const field = createFieldService(client); (client.request as jest.Mock).mockResolvedValue({});
    await field.arrival("20000000-0000-4000-8000-000000000001", "arrived", 4);
    await field.note("30000000-0000-4000-8000-000000000001", "Synthetic work completed", 3, 4);
    await field.approval("30000000-0000-4000-8000-000000000001", "approved", 3, 4);
    await field.refreshHandoff("30000000-0000-4000-8000-000000000001", 3, 4);
    const calls = (client.request as jest.Mock).mock.calls; const bodies = calls.map((call) => JSON.parse(call[2].body));
    expect(calls.map((call) => call[0])).not.toEqual(expect.arrayContaining([expect.stringMatching(/start|complete|finish|employee/i)]));
    for (const body of bodies) { expect(body).not.toHaveProperty("employee_id"); expect(body).not.toHaveProperty("timestamp"); expect(body.idempotency_key).toMatch(/^mobile:/); }
    expect(new Set(bodies.map((body) => body.idempotency_key)).size).toBe(4);
  });

  it("derives Payroll and field execution only from authoritative permissions", () => {
    expect(capabilitiesFromPermissions(["COMPANY_JOB_READ", "COMPANY_JOB_EXECUTE", "COMPANY_PAYROLL_STATEMENT_OWN_READ"])).toEqual(expect.arrayContaining(["jobs.view", "jobs.execute", "pay.self.view"]));
    expect(capabilitiesFromPermissions(["SUPERVISOR", "SALARIED", "TECHNICIAN"])).toEqual(["home.view"]);
  });
});
