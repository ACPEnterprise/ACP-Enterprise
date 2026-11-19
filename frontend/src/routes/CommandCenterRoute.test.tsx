import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuth } from "../auth/useAuth";
import { useEffectivePermissions } from "../auth/usePermissions";
import {
  useActiveBeaconRecommendations,
  useBeaconLifecycleActions,
  useBeaconSignals,
} from "../hooks/useBeaconSignals";
import { useDispatchBoard } from "../hooks/useDispatch";
import { useReceivablesSummary } from "../hooks/useInvoices";
import { useCompletedJobTrend } from "../hooks/useJobs";
import { useLuminaryBriefing } from "../hooks/useLuminary";
import { useMoneyPosition } from "../hooks/usePayments";
import { CommandCenterRoute } from "./CommandCenterRoute";

vi.mock("../auth/useAuth");
vi.mock("../auth/usePermissions");
vi.mock("../hooks/useBeaconSignals");
vi.mock("../hooks/useDispatch");
vi.mock("../hooks/useInvoices");
vi.mock("../hooks/useJobs");
vi.mock("../hooks/useLuminary");
vi.mock("../hooks/usePayments");

const permissions = new Set([
  "COMPANY_ANALYTICS_READ",
  "COMPANY_INVOICE_READ",
  "COMPANY_JOB_READ",
  "COMPANY_DISPATCH_READ",
  "COMPANY_PAYMENT_READ",
  "COMPANY_LUMINARY_READ",
  "COMPANY_BEACON_OWN",
]);

function result<T>(data: T) {
  return {
    data,
    isPending: false,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  } as never;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({
    user: { id: "owner-1" },
    activeCompany: {
      id: "company-1",
      name: "Demo Company",
      code: "DEMO",
      membership_id: "membership-1",
      default_branch_id: "branch-1",
      has_all_branch_access: true,
      branches: [
        { id: "branch-1", name: "Main", code: "MAIN", is_primary: true },
      ],
    },
  } as ReturnType<typeof useAuth>);
  vi.mocked(useEffectivePermissions).mockReturnValue(permissions);
  vi.mocked(useBeaconSignals).mockReturnValue(
    result({
      items: [],
      snoozed_items: [],
      evaluated_at: "2026-11-18T12:00:00Z",
      expires_at: "2026-11-18T12:15:00Z",
      lifecycle_commands_available: true,
      recommendation_coverage: [],
    }),
  );
  vi.mocked(useActiveBeaconRecommendations).mockReturnValue(
    result({ items: [], readiness_adapters: [] }),
  );
  vi.mocked(useBeaconLifecycleActions).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
  } as never);
  vi.mocked(useReceivablesSummary).mockReturnValue(
    result({
      currency: "USD",
      total_open_amount: "2400.00",
      open_invoice_count: 4,
      buckets: [
        {
          key: "past_due_31_plus",
          label: "31+ days",
          amount: "900.00",
          invoice_count: 1,
        },
      ],
    }),
  );
  vi.mocked(useCompletedJobTrend).mockReturnValue(
    result({
      currency: "USD",
      points: [
        { period_start: "2026-11-18", produced_value: "1500.00", job_count: 3 },
      ],
    }),
  );
  vi.mocked(useDispatchBoard).mockReturnValue(
    result({
      total_count: 2,
      items: [
        {
          appointment_id: "appointment-1",
          appointment_number: "APT-1",
          job_id: "job-1",
          branch_id: "branch-1",
          status: "confirmed",
          window_start_at: "2026-11-18T13:00:00Z",
          window_end_at: "2026-11-18T15:00:00Z",
          assignment: null,
        },
      ],
    }),
  );
  vi.mocked(useLuminaryBriefing).mockReturnValue(result({ findings: [] }));
  vi.mocked(useMoneyPosition).mockReturnValue(
    result({ bank_balance: { evidence_state: "UNAVAILABLE", amount: null } }),
  );
});

describe("CommandCenterRoute", () => {
  it("renders the owner hierarchy and truthful empty attention state", () => {
    render(
      <MemoryRouter>
        <CommandCenterRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", { name: "Command Center" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Needs Your Attention" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Nothing urgent needs your attention."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Business Pulse" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Recommended Actions / Ask LIA" }),
    ).toBeInTheDocument();
    expect(screen.getByText("$2,400")).toBeInTheDocument();
  });

  it("keeps exact action filters and passes finding records to LIA", () => {
    vi.mocked(useBeaconSignals).mockReturnValue(
      result({
        items: [
          {
            id: "11111111-1111-4111-8111-111111111111",
            condition_key: "22222222-2222-4222-8222-222222222222",
            evidence_digest: "a".repeat(64),
            definition_id: "operational.scheduling.appointment_unassigned",
            definition_version: 1,
            rule_code: "scheduling.unassigned",
            source: "scheduling",
            title: "2 jobs tomorrow are unassigned",
            category: "scheduling",
            severity: "important",
            priority: {
              band: "important",
              score: 80,
              rank: 1,
              ranking_factors: [],
              explanation: "Dispatch capacity is at risk.",
              evaluated_at: "2026-11-18T12:00:00Z",
              tie_break_semantics: "stable",
            },
            lifecycle: {
              status: "active",
              latest_event: null,
              temporarily_suppressed: false,
            },
            confidence: { level: "high", basis: "authoritative" },
            supporting_facts: [
              {
                name: "job_count",
                value: 2,
                source: "dispatch",
                measured_at: "2026-11-18T12:00:00Z",
                unit: "jobs",
                evidence: [
                  {
                    entity_type: "job",
                    entity_id: "33333333-3333-4333-8333-333333333333",
                    event_id: null,
                    event_type: null,
                    occurred_at: null,
                  },
                ],
              },
            ],
            recommended_action:
              "Assign the jobs before the operating day begins.",
            created_at: "2026-11-18T12:00:00Z",
            expires_at: "2026-11-18T12:15:00Z",
            expiration_policy: "replace_on_next_evaluation",
            escalation: null,
          },
        ],
        snoozed_items: [],
        evaluated_at: "2026-11-18T12:00:00Z",
        expires_at: "2026-11-18T12:15:00Z",
        lifecycle_commands_available: true,
        recommendation_coverage: [],
      } as never),
    );
    render(
      <MemoryRouter>
        <CommandCenterRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByText("2 jobs tomorrow are unassigned"),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: /Open Dispatch/ })[0],
    ).toHaveAttribute(
      "href",
      expect.stringContaining("queue=scheduled_unassigned"),
    );
    expect(screen.getByRole("link", { name: /Open job/ })).toHaveAttribute(
      "href",
      "/jobs/33333333-3333-4333-8333-333333333333",
    );
    expect(screen.getAllByRole("link", { name: /Ask LIA/ })[0]).toHaveAttribute(
      "href",
      expect.stringContaining(
        "contextRecord=job%3A33333333-3333-4333-8333-333333333333",
      ),
    );
    expect(
      screen.getByRole("link", { name: /Unassigned jobs today/ }),
    ).toHaveAttribute(
      "href",
      expect.stringContaining("queue=scheduled_unassigned"),
    );
  });
});
