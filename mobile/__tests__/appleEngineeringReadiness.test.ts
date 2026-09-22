import { AASA_URL, validateAasaDeployment } from "../src/operations/aasaDeployment";
import { generateAasa } from "../src/operations/betaContracts";

describe("engineering-owned Apple readiness", () => {
  it("validates exact AASA hosting and rejects redirects or changed bytes", () => {
    const body = generateAasa("ABCDE12345");
    const evidence = { requestedUrl: AASA_URL, responseUrl: AASA_URL, status: 200, contentType: "application/json; charset=utf-8", cacheControl: "public, max-age=3600", body };
    expect(() => validateAasaDeployment("ABCDE12345", evidence)).not.toThrow();
    expect(() => validateAasaDeployment("ABCDE12345", { ...evidence, responseUrl: "https://cdn.example/aasa" })).toThrow(/without redirect/);
    expect(() => validateAasaDeployment("ABCDE12345", { ...evidence, body: `${body} ` })).toThrow(/bytes/);
  });
});
