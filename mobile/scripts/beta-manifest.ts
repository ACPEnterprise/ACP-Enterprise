import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { AASA_VERSION, BUNDLE_ID, PREVIEW_API, sha256 } from "../src/operations/betaContracts";

const root = resolve("..");
const app = JSON.parse(readFileSync("app.json", "utf8")).expo;
const pkg = JSON.parse(readFileSync("package.json", "utf8"));
const release = JSON.parse(readFileSync("operations/beta-release.v1.json", "utf8"));
const git = (...args: string[]) => execFileSync("git", args, { cwd: root, encoding: "utf8" }).trim();
if (app.ios.bundleIdentifier !== BUNDLE_ID) throw new Error("Unexpected bundle identifier");
const manifest = {
  contract: "MOBILE.EMPLOYEE.BETA.OPERATIONS.1",
  gitSha: git("rev-parse", "HEAD"), mobileTreeSha: git("rev-parse", "HEAD:mobile"),
  appVersion: app.version, buildNumber: app.ios.buildNumber, bundleIdentifier: BUNDLE_ID,
  expoSdk: pkg.dependencies.expo, nativeDependencyDigest: sha256(readFileSync("ios/Podfile.lock")),
  environment: "preview", channel: "preview", apiBaseUrl: PREVIEW_API,
  entitlementsDigest: sha256(readFileSync("ios/ACPEmployee/ACPEmployee.entitlements")),
  aasaContractVersion: AASA_VERSION, signed: false, containsSecrets: false,
  releaseContractVersion: release.contractVersion, easCliVersion: release.easCliVersion,
};
const output = resolve(process.argv[2] ?? "build/beta/beta-build-manifest.json");
mkdirSync(dirname(output), { recursive: true });
writeFileSync(output, `${JSON.stringify(manifest, null, 2)}\n`);
console.info(output);
