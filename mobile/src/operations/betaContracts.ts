import { createHash } from "node:crypto";

export const BUNDLE_ID = "com.acpenterprise.employee";
export const PREVIEW_API = "https://preview.allcountyhomeservices.com";
export const ASSOCIATED_DOMAIN = "employee.acpenterprise.com";
export const AASA_VERSION = "1";
const TEAM_ID = /^[A-Z0-9]{10}$/;

export function generateAasa(teamId: string): string {
  if (!TEAM_ID.test(teamId)) throw new Error("APPLE_TEAM_ID must be exactly 10 uppercase letters or digits");
  return `${JSON.stringify({ applinks: { details: [{ appIDs: [`${teamId}.${BUNDLE_ID}`], components: [
    { "/": "/activate", comment: "ACP employee activation" },
    { "/": "/activate/*", comment: "ACP employee activation variants" },
  ] }] } }, null, 2)}\n`;
}

export function sha256(value: string | Buffer): string {
  return createHash("sha256").update(value).digest("hex");
}

export type FixtureContract = {
  contractVersion: string; environment: string; fixtureKey: string; syntheticMarker: string;
  permissions: string[]; prohibitedData: string[]; scenarios: string[];
  company: { externalKey: string; displayName: string };
  branch: { externalKey: string; displayName: string; timezone: string };
  user: { externalKey: string; loginPlaceholder: string };
  employee: { externalKey: string; displayName: string };
  customer: { externalKey: string; displayName: string };
  serviceLocation: { externalKey: string; address: string };
  job: { externalKey: string; serviceCategory: string };
  appointment: { externalKey: string; assignmentRole: string };
};

const requiredPermissions = ["COMPANY_TIMEKEEPING_OWN_READ", "COMPANY_TIMEKEEPING_OWN_PUNCH", "COMPANY_EMPLOYEE_OPERATIONS_OWN_DAY_READ", "COMPANY_JOB_READ", "COMPANY_JOB_EXECUTE", "COMPANY_ASSET_READ", "COMPANY_ESTIMATE_READ", "COMPANY_PAYROLL_STATEMENT_OWN_READ"];
const requiredScenarios = ["NO_ACTIVE_SHIFT", "CLOCKED_IN", "BREAK_ACTIVE", "CLOCKED_OUT", "MY_TIME_HISTORY", "MY_DAY_ONE_ASSIGNMENT", "JOB_WORKSPACE", "REASSIGNMENT_REMOVAL", "OFFLINE_STALE", "SESSION_EXPIRATION", "PERMISSION_DENIED", "NETWORK_RECOVERY", "FIELD_EVIDENCE", "EQUIPMENT_CONTEXT", "EQUIPMENT_HISTORY", "WARRANTY_EVIDENCE", "OWN_FLEET_READINESS", "ESTIMATE_PRESENTATION", "COMPLETED_JOB_HISTORY", "FOREIGN_ASSET_DENIED", "FOREIGN_ESTIMATE_DENIED", "BRANCH_REVOCATION", "ATTACHMENT_SOURCE_REQUIRED", "INSPECTION_POLICY_REQUIRED", "NOTIFICATION_SOURCE_REQUIRED", "PAYMENT_NOT_AUTHORIZED", "MY_PAY_STATEMENT", "PAYROLL_STATUS", "CORRECTED_STATEMENT", "YTD_UNAVAILABLE"];

export function validateFixture(contract: FixtureContract): void {
  if (contract.environment !== "preview" || contract.syntheticMarker !== "SYNTHETIC_BETA_ONLY") throw new Error("Fixture must be explicitly synthetic and Preview-only");
  if (contract.fixtureKey !== "acp-employee-beta-v1" || contract.user.loginPlaceholder !== "OWNER_SUPPLIED_SYNTHETIC_PREVIEW_LOGIN") throw new Error("Fixture identity contract is unsafe");
  const externalKeys = [contract.company.externalKey, contract.branch.externalKey, contract.user.externalKey, contract.employee.externalKey, contract.customer.externalKey, contract.serviceLocation.externalKey, contract.job.externalKey, contract.appointment.externalKey];
  if (!externalKeys.every((value) => value.startsWith("synthetic-beta-")) || new Set(externalKeys).size !== externalKeys.length) throw new Error("Fixture external identities must be unique and synthetic");
  if (!requiredPermissions.every((permission) => contract.permissions.includes(permission))) throw new Error("Fixture permission contract is incomplete");
  if (!requiredScenarios.every((scenario) => contract.scenarios.includes(scenario))) throw new Error("Fixture scenario contract is incomplete");
  if (!["compensation", "wage", "payroll_administration", "bank", "tax"].every((field) => contract.prohibitedData.includes(field))) throw new Error("Fixture prohibited-data contract is incomplete");
}

export type FixtureRecord = Readonly<{ kind: string; externalKey: string; value: unknown }>;
export type FixtureStore = {
  get(kind: string, externalKey: string): Promise<FixtureRecord | null>;
  create(record: FixtureRecord): Promise<void>;
  remove(kind: string, externalKey: string): Promise<void>;
};

export async function reconcileFixture(records: readonly FixtureRecord[], store: FixtureStore): Promise<{ created: number; existing: number }> {
  let created = 0; let existing = 0;
  for (const record of records) {
    if (!record.externalKey.startsWith("synthetic-beta-")) throw new Error("Fixture record lacks a synthetic external key");
    const current = await store.get(record.kind, record.externalKey);
    if (current) {
      if (JSON.stringify(current.value) !== JSON.stringify(record.value)) throw new Error(`Contradictory fixture: ${record.kind}/${record.externalKey}`);
      existing += 1;
    } else { await store.create(record); created += 1; }
  }
  return { created, existing };
}

export async function resetFixture(records: readonly FixtureRecord[], store: FixtureStore): Promise<void> {
  for (const record of [...records].reverse()) await store.remove(record.kind, record.externalKey);
}
