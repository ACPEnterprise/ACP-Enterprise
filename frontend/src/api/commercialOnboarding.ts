import { getQuickBooksSandboxConnection, getMigrationReadiness, type MigrationReadiness, type QboSandboxConnectionState } from "../features/administration/api";
import { getCandidateReview } from "./priceBook";
import { apiClient } from "./client";

export type CustomerProgressState =
  | "WAITING"
  | "IMPORTING"
  | "COMPLETE"
  | "NEEDS_REVIEW"
  | "NOT_AVAILABLE_FROM_SOURCE";

export interface CommercialProgressItem {
  id: string;
  label: string;
  state: CustomerProgressState;
  detail: string;
}

export interface CommercialException {
  id: string;
  domain: string;
  title: string;
  whyItMatters: string;
  recommendedAction: string;
}

export interface CommercialOnboardingEvidence {
  migrationAvailable: boolean;
  migrationMessage?: string;
  connections: Array<{
    id: string;
    label: string;
    state: "NOT CONNECTED" | "CONNECTED" | "IMPORTING" | "NEEDS ATTENTION" | "COMPLETE";
    detail: string;
  }>;
  progress: CommercialProgressItem[];
  exceptions: CommercialException[];
}

export interface MigrationSupportCase {
  id: string;
  company_id: string;
  onboarding_stage: string;
  source: string | null;
  domain: string | null;
  status: string;
  created_at: string;
}

export async function createMigrationSupportCase(input: {
  onboarding_stage: string;
  source?: string;
  domain?: string;
  message: string;
}): Promise<MigrationSupportCase> {
  return (await apiClient.post<MigrationSupportCase>("/api/v1/migration-support/cases", input)).data;
}

const domainLabels: Array<[string, string]> = [
  ["customers", "Customers"],
  ["jobs", "Jobs"],
  ["employees", "Employees"],
  ["price book", "Price Book"],
  ["estimates", "Estimates"],
  ["invoices", "Invoices"],
  ["payments", "Payments"],
  ["accounting", "Accounting"],
  ["payroll", "Payroll"],
  ["inventory", "Inventory"],
];

const normalize = (value: string) => value.trim().toLowerCase();

function stateForCount(item: MigrationReadiness["counts"][number]): CustomerProgressState {
  if (item.exception > 0 || item.held > 0 || item.unresolved > 0 || item.delta > 0) return "NEEDS_REVIEW";
  if (item.migrated > 0 || item.source === 0) return "COMPLETE";
  if (item.deferred > 0) return "WAITING";
  return "NOT_AVAILABLE_FROM_SOURCE";
}

function mapMigration(readiness: MigrationReadiness): {
  progress: CommercialProgressItem[];
  exceptions: CommercialException[];
} {
  const counts = new Map(readiness.counts.map((item) => [normalize(item.domain), item]));
  const progress: CommercialProgressItem[] = domainLabels.map(([id, label]) => {
    const item = [...counts.entries()].find(([domain]) => domain.includes(id) || id.includes(domain))?.[1];
    if (!item) return { id, label, state: "NOT_AVAILABLE_FROM_SOURCE", detail: "This source does not provide this information." };
    const state = stateForCount(item);
    const total = item.source || item.migrated;
    return {
      id,
      label,
      state,
      detail: state === "COMPLETE"
        ? `${item.migrated.toLocaleString()} records imported.`
        : state === "NEEDS_REVIEW"
          ? `${item.exception + item.held + item.unresolved + (item.delta > 0 ? item.delta : 0)} items need review.`
          : total === 0
            ? "No records were supplied by this source."
            : "Waiting for source evidence.",
    };
  });
  const exceptions = readiness.counts
    .filter((item) => item.exception > 0 || item.held > 0 || item.unresolved > 0 || item.delta > 0)
    .map((item) => ({
      id: `migration-${normalize(item.domain).replaceAll(" ", "-")}`,
      domain: item.domain,
      title: `${item.domain} needs a quick review`,
      whyItMatters: "TwelveHats found source records that do not agree cleanly yet.",
      recommendedAction: "Review the source evidence before treating this area as ready.",
    }));
  return { progress, exceptions };
}

export async function getCommercialOnboardingEvidence(): Promise<CommercialOnboardingEvidence> {
  const [migration, qbo, priceBook] = await Promise.allSettled([
    getMigrationReadiness(),
    getQuickBooksSandboxConnection(),
    getCandidateReview({ limit: 1, offset: 0 }),
  ]);
  const migrationValue = migration.status === "fulfilled" ? migration.value : undefined;
  const mapped = migrationValue ? mapMigration(migrationValue) : { progress: [], exceptions: [] };
  const qboState: QboSandboxConnectionState = qbo.status === "fulfilled" ? qbo.value : "unavailable";
  const connections: CommercialOnboardingEvidence["connections"] = [
    {
      id: "migration",
      label: "Previous service system",
      state: migrationValue ? (migrationValue.overall_status === "complete" ? "COMPLETE" : "NEEDS ATTENTION") : "NEEDS ATTENTION",
      detail: migrationValue ? "TwelveHats is showing the source-backed migration status." : "We could not read the current import status. Try again or get help.",
    },
    {
      id: "quickbooks",
      label: "QuickBooks",
      state: qboState === "connected" ? "CONNECTED" : qboState === "not_connected" ? "NOT CONNECTED" : "NEEDS ATTENTION",
      detail: qboState === "connected" ? "QuickBooks is connected for this Company." : "Connection status is not ready to use yet.",
    },
  ];
  const priceBookValue = priceBook.status === "fulfilled" ? priceBook.value : undefined;
  const candidateCounts = priceBookValue?.counts;
  const priceBookProgress: CommercialProgressItem = candidateCounts
    ? {
        id: "price-book",
        label: "Price Book",
        state: (candidateCounts.held ?? 0) > 0 || (candidateCounts.price_review_required ?? 0) > 0 ? "NEEDS_REVIEW" : "COMPLETE",
        detail: `${priceBookValue?.total.toLocaleString() ?? "Retained"} services are available for owner review; none were activated automatically.`,
      }
    : { id: "price-book", label: "Price Book", state: "NEEDS_REVIEW", detail: "Price Book status needs attention before activation." };
  const exceptions = [...mapped.exceptions];
  if (priceBook.status === "fulfilled" && (candidateCounts?.held ?? 0) > 0) {
    exceptions.push({
      id: "price-book-conflicts",
      domain: "Price Book",
      title: "Some services have competing prices",
      whyItMatters: "The source documents disagree, so TwelveHats is keeping those services held.",
      recommendedAction: "Review the competing source evidence and approve a price only when you are satisfied.",
    });
  }
  return {
    migrationAvailable: Boolean(migrationValue),
    migrationMessage: migrationValue ? undefined : "Import status is not available in this session. No completion has been assumed.",
    connections,
    progress: [...mapped.progress.filter((item) => item.id !== "price-book"), priceBookProgress],
    exceptions,
  };
}
