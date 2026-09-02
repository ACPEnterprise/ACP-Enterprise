import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const readJson = (path: string) => JSON.parse(readFileSync(path, "utf8"));
const app = readJson("app.json").expo;
const eas = readJson("eas.json");
const contract = readJson("operations/apple-distribution-readiness.v1.json");
const info = readFileSync("ios/ACPEmployee/Info.plist", "utf8");
const privacy = readFileSync("ios/ACPEmployee/PrivacyInfo.xcprivacy", "utf8");
const entitlements = readFileSync("ios/ACPEmployee/ACPEmployee.entitlements", "utf8");
const project = readFileSync("ios/ACPEmployee.xcodeproj/project.pbxproj", "utf8");

function assert(value: unknown, message: string): asserts value { if (!value) throw new Error(message); }
assert(contract.appleMutationAuthorized === false && contract.uploadAuthorized === false, "Apple mutation/upload must remain disabled");
assert(app.ios.bundleIdentifier === contract.bundleIdentifier && project.includes(`PRODUCT_BUNDLE_IDENTIFIER = ${contract.bundleIdentifier}`), "Bundle identifier mismatch");
assert(app.version === contract.currentLocalCandidate.version && app.ios.buildNumber === contract.currentLocalCandidate.build, "Version candidate mismatch");
assert(contract.currentLocalCandidate.uploaded === false && contract.versionPolicy.reuseUploadedBuild === false, "Build reuse must fail closed");
assert(eas.build.beta.channel === "preview" && eas.build.beta.env.EXPO_PUBLIC_API_BASE_URL === contract.previewDistribution.apiBaseUrl, "Beta is not Preview-pinned");
assert(eas.build.production.env.EXPO_PUBLIC_PRODUCTION_ACTIVATED === "false" && eas.build.production.env.EXPO_PUBLIC_API_BASE_URL.includes("example.invalid"), "Production must remain unusable");
assert(project.includes("IPHONEOS_DEPLOYMENT_TARGET = 16.4") && (project.match(/TARGETED_DEVICE_FAMILY = 1;/g) ?? []).length === 2 && app.ios.supportsTablet === false && app.orientation === "portrait", "Device/deployment contract mismatch");
assert(entitlements.includes(contract.universalLinks.associatedDomain), "Associated Domain missing");
assert(info.includes("<key>NSAllowsArbitraryLoads</key>") && info.includes("<false/>"), "ATS must fail closed");
for (const key of ["NSLocation", "NSContacts", "NSMicrophone", "NSBluetooth", "NSCamera", "NSPhotoLibrary", "UIBackgroundModes"]) assert(!info.includes(`<key>${key}`), `Unexpected permission: ${key}`);
assert(!entitlements.includes("aps-environment"), "Push entitlement must remain absent until notification authority exists");
assert(privacy.includes("<key>NSPrivacyTracking</key>") && privacy.includes("<false/>"), "Tracking declaration mismatch");
const icon = "ios/ACPEmployee/Images.xcassets/AppIcon.appiconset/App-Icon-1024x1024@1x.png";
const iconFacts = execFileSync("sips", ["-g", "pixelWidth", "-g", "pixelHeight", "-g", "hasAlpha", icon], { encoding: "utf8" });
assert(iconFacts.includes("pixelWidth: 1024") && iconFacts.includes("pixelHeight: 1024") && iconFacts.includes("hasAlpha: no"), "App Store icon must be opaque 1024x1024");
console.info("ACP Employee Apple distribution preflight passed without Apple account mutation.");
