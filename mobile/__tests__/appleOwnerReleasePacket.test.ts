import packet from "../operations/apple-owner-release-packet.v1.json";
import metadata from "../operations/app-store-connect-metadata.v1.json";

describe("Apple owner release packet", () => {
  it("binds to the qualified candidate and authorizes no external mutation", () => {
    expect(packet.sourceCandidate).toBe("bf28a61cfe7d36d0b050e0118b21b234c8a555e3");
    expect(packet.bundleIdentifier).toBe("com.acpenterprise.employee");
    expect(packet.environment).toBe("preview");
    expect(packet.productionActivated).toBe(false);
    expect(packet.appleMutationAuthorized).toBe(false);
    expect(packet.dnsMutationAuthorized).toBe(false);
    expect(packet.signingAuthorized).toBe(false);
    expect(packet.uploadAuthorized).toBe(false);
  });

  it("keeps legal, URL, Team, SKU and privacy choices owner-controlled", () => {
    expect(packet.ownerConfirmationRequired).toEqual(expect.arrayContaining(["authoritative Team ID", "support and privacy-policy URLs", "privacy questionnaire and legal interpretation", "immutable SKU"]));
    expect(packet.appleAccountRequired).toContain("explicit App ID and Associated Domains capability");
    expect(metadata.supportUrl).toMatch(/^OWNER_REQUIRED_/);
    expect(metadata.privacyPolicyUrl).toMatch(/^OWNER_REQUIRED_/);
    expect(metadata.sku).toMatch(/^OWNER_REQUIRED_/);
  });

});
