import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ServiceAgreementsRoute } from "./ServiceAgreementsRoute";
let permissions = new Set<string>();
vi.mock("../auth", () => ({
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../api/serviceAgreements", () => ({
  getAgreementWorkspace: vi
    .fn()
    .mockResolvedValue({
      agreements: [
        {
          id: "a1",
          agreement_number: "AGR-000001",
          customer_id: "c1",
          status: "active",
          start_date: "2026-01-01",
          end_date: "2026-12-31",
          version: 1,
          plan_snapshot: {},
        },
      ],
      entitlements: [],
      active_count: 1,
      renewal_pending_count: 0,
      service_due_count: 0,
      billing_unconfigured_count: 1,
    }),
  listAgreementPlans: vi.fn().mockResolvedValue([]),
  createAgreementPlan: vi.fn(),
  activateAgreementPlan: vi.fn(),
  enrollAgreement: vi.fn(),
  transitionAgreement: vi.fn(),
  generateEntitlements: vi.fn(),
}));
const show = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ServiceAgreementsRoute />
    </QueryClientProvider>,
  );
describe("ServiceAgreementsRoute", () => {
  beforeEach(() => (permissions = new Set()));
  it("fails closed without read authority", () => {
    show();
    expect(screen.getByText(/not authorized/)).toBeVisible();
  });
  it("keeps read-only agreement evidence visible without lifecycle controls", async () => {
    permissions = new Set(["COMPANY_SERVICE_AGREEMENT_READ"]);
    show();
    expect(await screen.findByText("AGR-000001")).toBeVisible();
    expect(
      screen.queryByText("Generate service obligations"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Enroll a Customer")).not.toBeInTheDocument();
  });
  it("exposes governed controls to managers", async () => {
    permissions = new Set([
      "COMPANY_SERVICE_AGREEMENT_READ",
      "COMPANY_SERVICE_AGREEMENT_MANAGE",
    ]);
    show();
    expect(
      await screen.findByText("Generate service obligations"),
    ).toBeVisible();
    expect(screen.getByText("Enroll a Customer")).toBeVisible();
  });
});
