import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const app = JSON.parse(readFileSync("app.json", "utf8")).expo;
const eas = JSON.parse(readFileSync("eas.json", "utf8"));
const release = JSON.parse(readFileSync("operations/beta-release.v1.json", "utf8"));
const privacy = readFileSync("ios/ACPEmployee/PrivacyInfo.xcprivacy", "utf8");
const entitlements = readFileSync("ios/ACPEmployee/ACPEmployee.entitlements", "utf8");
if (app.ios.bundleIdentifier !== "com.acpenterprise.employee") throw new Error("Bundle ID mismatch");
if (!app.ios.associatedDomains.includes("applinks:employee.acpenterprise.com")) throw new Error("Associated Domain missing");
if (eas.build.beta.channel !== "preview" || eas.build.beta.env.EXPO_PUBLIC_API_BASE_URL !== "https://preview.allcountyhomeservices.com") throw new Error("Beta is not Preview-pinned");
if (eas.build.production.env.EXPO_PUBLIC_PRODUCTION_ACTIVATED !== "false" || !eas.build.production.env.EXPO_PUBLIC_API_BASE_URL.includes("example.invalid")) throw new Error("Production does not fail closed");
if (release.environment !== "preview" || release.channel !== "preview" || release.signed !== false || release.easCliVersion !== "16.28.0") throw new Error("Beta release contract mismatch");
if (!privacy.includes("<false/>") || !entitlements.includes("applinks:employee.acpenterprise.com")) throw new Error("Privacy/entitlement contract mismatch");
for (const args of [["run", "config:validate"], ["run", "typecheck"], ["run", "lint"], ["test", "--", "--runInBand"], ["run", "beta:fixture"]]) execFileSync("npm", args, { stdio: "inherit" });
execFileSync("npm", ["run", "beta:manifest"], { stdio: "inherit" });
console.info("ACP Employee unsigned beta operational preflight passed.");
