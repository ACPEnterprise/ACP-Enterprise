import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EconomicsPolicyAdministrationRoute } from "./EconomicsPolicyAdministrationRoute";

const permissions = new Set<string>();
let lineageData: Record<string, unknown> | null = null;
vi.mock("../auth", () => ({
  useHasPermission: (code: string) => permissions.has(code),
}));
vi.mock("../hooks/useBusinessEconomics", () => ({
  useEconomicsResultLineage: () => ({
    isPending: false,
    isError: false,
    data: lineageData,
  }),
  useEconomicsPolicyAdministration: (
    _start: string,
    _end: string,
    enabled: boolean,
  ) => ({
    isPending: false,
    isError: false,
    refetch: vi.fn(),
    data: enabled
      ? {
          administration_fingerprint: "a".repeat(64),
          readiness: {
            sources: [
              {
                source: "revenue",
                state: "AVAILABLE",
                evidence_count: 2,
                explanation: "Accepted earned evidence.",
              },
              {
                source: "overhead_allocation",
                state: "POLICY_REQUIRED",
                evidence_count: 2,
                explanation: "Owner policy is required.",
              },
            ],
          },
          policy_families: [
            {
              family_key: "overhead_allocation",
              title: "Overhead allocation",
              decision_id: "ECO-FIN-008",
              state: "OWNER_DECISION_REQUIRED",
              current_policy_id: null,
              current_version: null,
              current_strategy: null,
              supported_strategies: ["approved_allocation_drivers"],
              required_parameter_keys: ["driver_definition_refs"],
              configured_parameter_keys: [],
              effective_start: null,
              policy_digest: null,
            },
          ],
          policy_history: [],
          policy_gaps: [],
          policy_snapshots: [],
          mutation_authority: "none",
        }
      : null,
  }),
}));

describe("Economics policy administration", () => {
  beforeEach(() => {
    permissions.clear();
    lineageData = null;
  });

  it("fails closed without policy-read authority", () => {
    render(
      <MemoryRouter>
        <EconomicsPolicyAdministrationRoute />
      </MemoryRouter>,
    );
    expect(screen.getByText(/not authorized/i)).toBeVisible();
  });

  it("shows truthful readiness, unconfigured policy, and interpretation navigation", () => {
    permissions.add("COMPANY_ECONOMICS_POLICY_READ");
    render(
      <MemoryRouter>
        <EconomicsPolicyAdministrationRoute />
      </MemoryRouter>,
    );
    expect(screen.getByText("revenue")).toBeVisible();
    expect(screen.getAllByText(/policy required/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/1 policy decision/i)).toBeVisible();
    expect(screen.getByText("approved allocation drivers")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open Luminary interpretation" }),
    ).toHaveAttribute("href", "/luminary");
    expect(screen.getByRole("link", { name: "Ask LIA" })).toHaveAttribute(
      "href",
      "/lia",
    );
    expect(screen.getByLabelText("Economics readiness")).toHaveClass(
      "sm:grid-cols-2",
    );
  });

  it("does not expose result history without measurement-read authority", () => {
    permissions.add("COMPANY_ECONOMICS_POLICY_READ");
    render(
      <MemoryRouter>
        <EconomicsPolicyAdministrationRoute />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(/measurement-read authority is required/i),
    ).toBeVisible();
  });

  it("distinguishes current and historical immutable result authority", () => {
    permissions.add("COMPANY_ECONOMICS_POLICY_READ");
    permissions.add("COMPANY_ECONOMICS_MEASUREMENT_READ");
    lineageData = {
      current_result_id: "22222222-2222-2222-2222-222222222222",
      results: [
        {
          result_id: "11111111-1111-1111-1111-111111111111",
          authority_state: "historical",
          result_digest: "a".repeat(64),
          package_digest: "b".repeat(64),
          computation_digest: "c".repeat(64),
          period_start: "2026-08-01",
          period_end: "2026-08-31",
          currency: "USD",
          predecessor_result_id: null,
          successor_result_id: "22222222-2222-2222-2222-222222222222",
          supersession_reason: "source_correction",
          limitations: ["Material evidence is partial."],
        },
        {
          result_id: "22222222-2222-2222-2222-222222222222",
          authority_state: "current",
          result_digest: "d".repeat(64),
          package_digest: "e".repeat(64),
          computation_digest: "f".repeat(64),
          period_start: "2026-08-01",
          period_end: "2026-08-31",
          currency: "USD",
          predecessor_result_id: "11111111-1111-1111-1111-111111111111",
          successor_result_id: null,
          supersession_reason: null,
          limitations: [],
        },
      ],
    };

    render(
      <MemoryRouter>
        <EconomicsPolicyAdministrationRoute />
      </MemoryRouter>,
    );
    expect(screen.getByText(/historical · source correction/i)).toBeVisible();
    expect(screen.getByText(/current · original result/i)).toBeVisible();
    expect(screen.getByText(/material evidence is partial/i)).toBeVisible();
  });
});
