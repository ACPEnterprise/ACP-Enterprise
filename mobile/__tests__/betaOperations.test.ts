import { generateAasa, reconcileFixture, resetFixture, validateFixture, type FixtureRecord } from "../src/operations/betaContracts";
import fixture from "../operations/beta-fixture.v1.json";
import { isActivationLink } from "../src/linking/linking";
import { safeBuildIdentity } from "../src/diagnostics/buildIdentity";
import template from "../operations/aasa.template.json";
import { provisionPreviewFixture, resetPreviewFixture, type PreviewFixtureAdapter } from "../src/operations/betaFixtureProvisioning";

describe("beta operations contracts", () => {
  it("generates only the bounded activation AASA contract", () => {
    const aasa = JSON.parse(generateAasa("A1B2C3D4E5"));
    expect(aasa.applinks.details[0].appIDs).toEqual(["A1B2C3D4E5.com.acpenterprise.employee"]);
    expect(aasa.applinks.details[0].components.map((item: Record<string, string>) => item["/"])).toEqual(["/activate", "/activate/*"]);
    expect(JSON.stringify(aasa)).not.toMatch(/token|secret/i);
    expect(JSON.stringify(template).replace("${APPLE_TEAM_ID}", "A1B2C3D4E5")).toBe(JSON.stringify(aasa));
  });
  it("fails closed without an authoritative Apple Team ID", () => expect(() => generateAasa("<APPLE_TEAM_ID>")).toThrow());
  it("qualifies the deterministic synthetic Preview fixture", () => expect(() => validateFixture(fixture)).not.toThrow());
  it("proves idempotent fixture reconciliation, contradiction detection, and bounded reset", async () => {
    const values = new Map<string, FixtureRecord>();
    const store = { get: async (kind: string, key: string) => values.get(`${kind}/${key}`) ?? null, create: async (record: FixtureRecord) => { values.set(`${record.kind}/${record.externalKey}`, record); }, remove: async (kind: string, key: string) => { values.delete(`${kind}/${key}`); } };
    const records = [{ kind: "company", externalKey: "synthetic-beta-company", value: { name: "Synthetic Beta Services" } }] as const;
    await expect(reconcileFixture(records, store)).resolves.toEqual({ created: 1, existing: 0 });
    await expect(reconcileFixture(records, store)).resolves.toEqual({ created: 0, existing: 1 });
    await expect(reconcileFixture([{ ...records[0], value: { name: "Contradiction" } }], store)).rejects.toThrow("Contradictory fixture");
    await resetFixture(records, store); expect(values.size).toBe(0);
  });
  it("fails closed and orders Preview provisioning and domain-safe reset", async () => {
    const values = new Map<string, FixtureRecord>(); const events: string[] = [];
    const adapter: PreviewFixtureAdapter = {
      inspect: async (record) => values.get(`${record.kind}/${record.externalKey}`) ?? null,
      provision: async (record) => { events.push(`create:${record.kind}`); values.set(`${record.kind}/${record.externalKey}`, record); },
      revokeInvitation: async () => { events.push("revoke:invitation"); }, revokeSessions: async () => { events.push("revoke:sessions"); },
      clearOperationalEvidence: async () => { events.push("clear:evidence"); },
      remove: async (record) => { events.push(`remove:${record.kind}`); values.delete(`${record.kind}/${record.externalKey}`); },
    };
    const authorization = { environment: "preview", fixtureKey: fixture.fixtureKey, fixtureAuthorized: true, syntheticLogin: "technician@acp-fixture.invalid" };
    await expect(provisionPreviewFixture(fixture, { ...authorization, environment: "production" }, adapter)).rejects.toThrow("explicit Preview authorization");
    await expect(provisionPreviewFixture(fixture, { ...authorization, syntheticLogin: "real@example.com" }, adapter)).rejects.toThrow(".invalid");
    await expect(provisionPreviewFixture(fixture, authorization, adapter)).resolves.toEqual({ created: 11, existing: 0 });
    await expect(provisionPreviewFixture(fixture, authorization, adapter)).resolves.toEqual({ created: 0, existing: 11 });
    await resetPreviewFixture(fixture, authorization, adapter);
    expect(values.size).toBe(0);
    expect(events.slice(11, 14)).toEqual(["revoke:invitation", "revoke:sessions", "clear:evidence"]);
    expect(events.slice(14)).toEqual(["remove:assignment", "remove:appointment", "remove:job", "remove:serviceLocation", "remove:customer", "remove:employee", "remove:branchGrant", "remove:membership", "remove:user", "remove:branch", "remove:company"]);
  });
  it("accepts only activation links with a non-empty transient token", () => {
    expect(isActivationLink("https://employee.acpenterprise.com/activate?token=opaque-reference")).toBe(true);
    expect(isActivationLink("acpemployee://activate?token=opaque-reference")).toBe(true);
    expect(isActivationLink("https://employee.acpenterprise.com/other?token=opaque-reference")).toBe(false);
    expect(isActivationLink("https://employee.acpenterprise.com/activate?token=")).toBe(false);
    expect(isActivationLink("https://untrusted.example/activate?token=opaque-reference")).toBe(false);
  });
  it("exposes only non-secret runtime beta identity", () => {
    const identity = safeBuildIdentity({ environment: "preview", apiBaseUrl: "https://preview.allcountyhomeservices.com", compatibilityVersion: "2026-08-01" });
    expect(identity).toMatchObject({ product: "ACP Employee", environment: "preview", channel: "preview", compatibilityVersion: "2026-08-01" });
    expect(JSON.stringify(identity)).not.toMatch(/token|password|credential|apiBaseUrl/i);
  });
});
