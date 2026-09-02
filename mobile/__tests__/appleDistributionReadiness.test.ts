import contract from "../operations/apple-distribution-readiness.v1.json";

describe("Apple distribution readiness contract", () => {
  it("pins beta to Preview and prohibits Apple mutation/upload", () => {
    expect(contract.bundleIdentifier).toBe("com.acpenterprise.employee");
    expect(contract.previewDistribution.apiBaseUrl).toBe("https://preview.allcountyhomeservices.com");
    expect(contract.productionDistribution.authorized).toBe(false);
    expect(contract.appleMutationAuthorized).toBe(false);
    expect(contract.uploadAuthorized).toBe(false);
  });

  it("prohibits uploaded build-number reuse", () => {
    expect(contract.currentLocalCandidate.uploaded).toBe(false);
    expect(contract.versionPolicy.reuseUploadedBuild).toBe(false);
    expect(contract.versionPolicy.sourceOfTruthAfterFirstUpload).toContain("App Store Connect");
  });
});
