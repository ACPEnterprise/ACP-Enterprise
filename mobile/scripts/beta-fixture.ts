import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { FixtureContract, sha256, validateFixture } from "../src/operations/betaContracts";

const contractPath = resolve("operations/beta-fixture.v1.json");
const bytes = readFileSync(contractPath);
const contract = JSON.parse(bytes.toString("utf8")) as FixtureContract;
validateFixture(contract);
if (process.argv.includes("--apply")) {
  if (process.env.ACP_ENVIRONMENT !== "preview" || process.env.ACP_BETA_FIXTURE_AUTHORIZED !== "true") throw new Error("Fixture application requires Preview plus ACP_BETA_FIXTURE_AUTHORIZED=true");
  throw new Error("Preview mutation is intentionally unavailable in BETA.OPERATIONS.1; use the accepted domain provisioning adapter after separate authorization");
}
console.info(JSON.stringify({ mode: "dry-run", fixtureKey: contract.fixtureKey, contractDigest: sha256(bytes), scenarios: contract.scenarios, mutationPerformed: false }, null, 2));
