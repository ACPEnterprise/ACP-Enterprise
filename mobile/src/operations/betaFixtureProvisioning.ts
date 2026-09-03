import type { FixtureContract, FixtureRecord } from "./betaContracts";
import { validateFixture } from "./betaContracts";

export type PreviewFixtureAuthorization = Readonly<{ environment: string; fixtureKey: string; fixtureAuthorized: boolean; syntheticLogin: string }>;

export type PreviewFixtureAdapter = Readonly<{
  inspect(record: FixtureRecord): Promise<FixtureRecord | null>;
  provision(record: FixtureRecord): Promise<void>;
  revokeInvitation(fixtureKey: string): Promise<void>;
  revokeSessions(fixtureKey: string): Promise<void>;
  clearOperationalEvidence(fixtureKey: string): Promise<void>;
  remove(record: FixtureRecord): Promise<void>;
}>;

const kinds = ["company", "branch", "user", "membership", "branchGrant", "employee", "customer", "serviceLocation", "job", "appointment", "assignment"] as const;

function authorize(contract: FixtureContract, authorization: PreviewFixtureAuthorization): void {
  validateFixture(contract);
  if (authorization.environment !== "preview" || !authorization.fixtureAuthorized) throw new Error("Fixture mutation requires explicit Preview authorization");
  if (authorization.fixtureKey !== contract.fixtureKey) throw new Error("Fixture authorization does not match the contract");
  const login = authorization.syntheticLogin.trim().toLowerCase();
  if (!login.endsWith(".invalid") || login.includes("@allcounty")) throw new Error("Fixture login must use a non-routable synthetic .invalid identity");
}

export function previewFixtureRecords(contract: FixtureContract, syntheticLogin: string): readonly FixtureRecord[] {
  validateFixture(contract);
  return [
    { kind: "company", externalKey: contract.company.externalKey, value: { displayName: contract.company.displayName, marker: contract.syntheticMarker } },
    { kind: "branch", externalKey: contract.branch.externalKey, value: { displayName: contract.branch.displayName, timezone: contract.branch.timezone, marker: contract.syntheticMarker } },
    { kind: "user", externalKey: contract.user.externalKey, value: { login: syntheticLogin.trim().toLowerCase(), marker: contract.syntheticMarker } },
    { kind: "membership", externalKey: "synthetic-beta-membership", value: { companyExternalKey: contract.company.externalKey, userExternalKey: contract.user.externalKey, marker: contract.syntheticMarker } },
    { kind: "branchGrant", externalKey: "synthetic-beta-branch-grant", value: { branchExternalKey: contract.branch.externalKey, userExternalKey: contract.user.externalKey, marker: contract.syntheticMarker } },
    { kind: "employee", externalKey: contract.employee.externalKey, value: { displayName: contract.employee.displayName, userExternalKey: contract.user.externalKey, permissions: [...contract.permissions].sort(), marker: contract.syntheticMarker } },
    { kind: "customer", externalKey: contract.customer.externalKey, value: { displayName: contract.customer.displayName, marker: contract.syntheticMarker } },
    { kind: "serviceLocation", externalKey: contract.serviceLocation.externalKey, value: { address: contract.serviceLocation.address, customerExternalKey: contract.customer.externalKey, marker: contract.syntheticMarker } },
    { kind: "job", externalKey: contract.job.externalKey, value: { serviceCategory: contract.job.serviceCategory, serviceLocationExternalKey: contract.serviceLocation.externalKey, marker: contract.syntheticMarker } },
    { kind: "appointment", externalKey: contract.appointment.externalKey, value: { jobExternalKey: contract.job.externalKey, marker: contract.syntheticMarker } },
    { kind: "assignment", externalKey: "synthetic-beta-assignment", value: { appointmentExternalKey: contract.appointment.externalKey, employeeExternalKey: contract.employee.externalKey, role: contract.appointment.assignmentRole, marker: contract.syntheticMarker } },
  ];
}

function equal(left: unknown, right: unknown): boolean { return JSON.stringify(left) === JSON.stringify(right); }

export async function provisionPreviewFixture(contract: FixtureContract, authorization: PreviewFixtureAuthorization, adapter: PreviewFixtureAdapter): Promise<{ created: number; existing: number }> {
  authorize(contract, authorization);
  let created = 0; let existing = 0;
  for (const record of previewFixtureRecords(contract, authorization.syntheticLogin)) {
    const current = await adapter.inspect(record);
    if (current) {
      if (current.externalKey !== record.externalKey || current.kind !== record.kind || !equal(current.value, record.value)) throw new Error(`Contradictory fixture: ${record.kind}/${record.externalKey}`);
      existing += 1;
    } else { await adapter.provision(record); created += 1; }
  }
  return { created, existing };
}

export async function resetPreviewFixture(contract: FixtureContract, authorization: PreviewFixtureAuthorization, adapter: PreviewFixtureAdapter): Promise<void> {
  authorize(contract, authorization);
  const records = previewFixtureRecords(contract, authorization.syntheticLogin);
  await adapter.revokeInvitation(contract.fixtureKey);
  await adapter.revokeSessions(contract.fixtureKey);
  await adapter.clearOperationalEvidence(contract.fixtureKey);
  for (const kind of [...kinds].reverse()) {
    const record = records.find((value) => value.kind === kind);
    if (!record) throw new Error(`Fixture reset plan is incomplete: ${kind}`);
    const current = await adapter.inspect(record);
    if (!current) continue;
    if (current.externalKey !== record.externalKey || current.kind !== record.kind || !equal(current.value, record.value)) throw new Error(`Refusing to remove contradictory fixture: ${record.kind}/${record.externalKey}`);
    await adapter.remove(record);
  }
}
