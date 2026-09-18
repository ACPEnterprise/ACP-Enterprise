import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const readJson = (path: string) => JSON.parse(readFileSync(path, "utf8"));
const app = readJson("app.json").expo;
const eas = readJson("eas.json");
const info = readFileSync("ios/ACPEmployee/Info.plist", "utf8");
const privacy = readFileSync("ios/ACPEmployee/PrivacyInfo.xcprivacy", "utf8");
const entitlements = readFileSync("ios/ACPEmployee/ACPEmployee.entitlements", "utf8");
const project = readFileSync("ios/ACPEmployee.xcodeproj/project.pbxproj", "utf8");
const previewApi = "https://preview.allcountyhomeservices.com";
const previewConfig = JSON.parse(execFileSync("npx", ["expo", "config", "--json"], {
  encoding: "utf8",
  env: { ...process.env, EXPO_PUBLIC_APP_ENV: "preview", EXPO_PUBLIC_API_BASE_URL: previewApi, EXPO_PUBLIC_PRODUCTION_ACTIVATED: "false" },
}));

function assert(value: unknown, message: string): asserts value {
  if (!value) throw new Error(message);
}

assert(app.ios.bundleIdentifier === "com.acpenterprise.employee", "Bundle identifier changed");
assert(project.includes(`PRODUCT_BUNDLE_IDENTIFIER = ${app.ios.bundleIdentifier}`), "Native bundle identifier mismatch");
assert((project.match(new RegExp(`CURRENT_PROJECT_VERSION = ${app.ios.buildNumber};`, "g")) ?? []).length === 2, "Native build number mismatch");
assert(eas.build.beta.channel === "preview" && eas.build.beta.env.EXPO_PUBLIC_API_BASE_URL === previewApi, "Beta must remain Preview-pinned");
assert(previewConfig.extra.environment === "preview" && previewConfig.extra.apiBaseUrl === previewApi && previewConfig.extra.productionActivated === false, "Resolved Preview configuration mismatch");
assert(eas.build.production.env.EXPO_PUBLIC_PRODUCTION_ACTIVATED === "false" && eas.build.production.env.EXPO_PUBLIC_API_BASE_URL.includes("example.invalid"), "Production must remain unusable");
assert(entitlements.includes("applinks:employee.acpenterprise.com"), "Associated Domain missing");
assert(info.includes("<key>NSAllowsArbitraryLoads</key>") && info.includes("<false/>"), "ATS must fail closed");
for (const key of ["NSLocation", "NSContacts", "NSMicrophone", "NSBluetooth", "NSCamera", "NSPhotoLibrary", "UIBackgroundModes"]) {
  assert(!info.includes(`<key>${key}`), `Unexpected permission: ${key}`);
}
assert(!entitlements.includes("aps-environment"), "Push entitlement requires separate authority");
assert(privacy.includes("<key>NSPrivacyTracking</key>") && privacy.includes("<false/>"), "Tracking declaration mismatch");
const iconFacts = execFileSync("sips", ["-g", "pixelWidth", "-g", "pixelHeight", "-g", "hasAlpha", "assets/app-icon.png"], { encoding: "utf8" });
assert(iconFacts.includes("pixelWidth: 1024") && iconFacts.includes("pixelHeight: 1024") && iconFacts.includes("hasAlpha: no"), "App icon must be opaque 1024x1024");
console.info("ACP Employee engineering-owned Apple readiness passed; no signing, upload, or provider mutation was performed.");
