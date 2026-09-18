import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

import rollout from "../operations/employee-rollout-3day.v1.json";
import acceptance from "../operations/internal-testflight-acceptance.v1.json";
import { generateAasa } from "../src/operations/betaContracts";

describe("controlled employee rollout", () => {
  it("binds the uploaded candidate to Preview and prohibits build reuse", () => {
    expect(rollout.bundleIdentifier).toBe("com.acpenterprise.employee");
    expect(rollout.teamId).toBe("74R6X48GHA");
    expect(rollout.distribution).toBe("internal-testflight");
    expect(rollout.environment).toBe("preview");
    expect(rollout.apiBaseUrl).toBe("https://preview.allcountyhomeservices.com");
    expect(rollout.productionActivated).toBe(false);
    expect(rollout.buildReuseAllowed).toBe(false);
    expect(rollout.upload.publicSubmission).toBe(false);
  });

  it("uses the approved opaque Apple icon in Expo and the native asset catalog", () => {
    const expoIcon = readFileSync("assets/app-icon.png");
    const nativeIcon = readFileSync("ios/ACPEmployee/Images.xcassets/AppIcon.appiconset/App-Icon-1024x1024@1x.png");
    const digest = (value: Buffer) => createHash("sha256").update(value).digest("hex");
    expect(digest(expoIcon)).toBe(rollout.branding.iconSha256);
    expect(digest(nativeIcon)).toBe(rollout.branding.iconSha256);
  });

  it("publishes the exact Team-bound AASA candidate without activation secrets", () => {
    const aasa = readFileSync("operations/apple-app-site-association", "utf8");
    expect(aasa).toBe(generateAasa(rollout.teamId));
    expect(aasa).toContain(rollout.aasaAppId);
    expect(aasa).not.toMatch(/token|secret|password/i);
  });

  it("keeps the employee acceptance roster credential-free and Preview-only", () => {
    expect(acceptance.environment).toBe("preview");
    expect(acceptance.apiBaseUrl).toBe("https://preview.allcountyhomeservices.com");
    expect(acceptance.testerSelection.credentialsInRepository).toBe(false);
    expect(JSON.stringify(acceptance.testerSelection)).not.toMatch(/@/);
    expect(acceptance.stopConditions).toContain("Production endpoint appears");
  });
});
