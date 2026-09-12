import metadata from "../operations/app-store-connect-metadata.v1.json";
import privacy from "../operations/app-store-privacy-evidence.v1.json";
import hosting from "../operations/aasa-hosting.v1.json";
import { AASA_URL, validateAasaDeployment } from "../src/operations/aasaDeployment";
import { generateAasa } from "../src/operations/betaContracts";

describe("distribution package", () => {
  it("binds Store metadata to the accepted candidate without inventing owner values", () => {
    expect(metadata.appName).toBe("ACP Employee");
    expect(metadata.bundleIdentifier).toBe("com.acpenterprise.employee");
    expect(metadata.subtitleDraft.length).toBeLessThanOrEqual(30);
    expect(metadata.localCandidate.uploaded).toBe(false);
    expect(metadata.supportUrl).toMatch(/^OWNER_REQUIRED_/);
    expect(metadata.privacyPolicyUrl).toMatch(/^OWNER_REQUIRED_/);
    expect(metadata.ownerDecisionsRequired.length).toBeGreaterThan(0);
  });

  it("records behavior-derived privacy evidence and gated capabilities", () => {
    expect(privacy.tracking).toBe(false);
    expect(privacy.thirdPartyAnalytics).toBe(false);
    expect(privacy.evidence.find((item) => item.category === "identity_account")?.accessed).toBe(true);
    expect(privacy.evidence.find((item) => item.category === "financial_information")?.accessed).toBe(true);
    expect(privacy.evidence.find((item) => item.category === "precise_or_coarse_location")?.accessed).toBe(false);
    expect(privacy.evidence.find((item) => item.category === "photos_camera_microphone")?.accessed).toBe(false);
    expect(privacy.submissionGate).toContain("Owner/legal");
  });

  it("validates exact AASA hosting evidence and rejects redirects or changed bytes", () => {
    const body = generateAasa("ABCDE12345");
    const evidence = { requestedUrl: AASA_URL, responseUrl: AASA_URL, status: 200, contentType: "application/json; charset=utf-8", cacheControl: "public, max-age=3600", body };
    expect(() => validateAasaDeployment("ABCDE12345", evidence)).not.toThrow();
    expect(() => validateAasaDeployment("ABCDE12345", { ...evidence, responseUrl: "https://cdn.example/aasa" })).toThrow(/without redirect/);
    expect(() => validateAasaDeployment("ABCDE12345", { ...evidence, body: `${body} ` })).toThrow(/bytes/);
    expect(hosting.dnsMutationAuthorized).toBe(false);
    expect(hosting.teamIdKnown).toBe(false);
  });
});
