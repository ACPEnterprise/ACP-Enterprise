import { readFileSync } from "node:fs";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const app = JSON.parse(read("../app.json")).expo;
const eas = JSON.parse(read("../eas.json"));
const info = read("../ios/ACPEmployee/Info.plist");
const project = read("../ios/ACPEmployee.xcodeproj/project.pbxproj");
const gradle = read("../android/app/build.gradle");
const manifest = read("../android/app/src/main/AndroidManifest.xml");
const entitlements = read("../ios/ACPEmployee/ACPEmployee.entitlements");

const requireConfig: (condition: unknown, message: string) => asserts condition = (condition, message) => {
  if (!condition) throw new Error(message);
};

const identifier = "com.acpenterprise.employee";
const previewUrl = "https://preview.allcountyhomeservices.com";
requireConfig(app.name === "ACP Employee", "Display identity must be ACP Employee");
requireConfig(app.ios?.bundleIdentifier === identifier && app.android?.package === identifier, "Native identifiers must be stable");
requireConfig(app.version === "0.1.0" && app.ios.buildNumber === "1" && app.android.versionCode === 1, "Expo version metadata must be explicit");
requireConfig(info.includes("<string>0.1.0</string>") && info.includes("<string>1</string>"), "iOS plist version metadata must match Expo");
requireConfig((project.match(/MARKETING_VERSION = 0\.1\.0;/g) ?? []).length === 2 && (project.match(/CURRENT_PROJECT_VERSION = 1;/g) ?? []).length === 2, "Xcode version metadata must match Expo");
requireConfig(gradle.includes("versionCode 1") && gradle.includes('versionName "0.1.0"'), "Android version metadata must match Expo");
requireConfig(app.updates?.enabled === false, "Remote updates must remain inactive");
requireConfig(app.extra?.productionActivated === false, "Production must be inactive by default");
requireConfig(eas.build.preview.env.EXPO_PUBLIC_API_BASE_URL === previewUrl && eas.build.beta.env.EXPO_PUBLIC_API_BASE_URL === previewUrl, "Preview and beta builds must use the authorized Preview API");
requireConfig(eas.build.beta.distribution === "store" && eas.build.beta.channel === "preview", "Beta distribution must remain isolated on Preview");
requireConfig(eas.build.production.env.EXPO_PUBLIC_PRODUCTION_ACTIVATED === "false" && eas.build.production.env.EXPO_PUBLIC_API_BASE_URL.includes("example.invalid"), "Production must fail closed");
requireConfig(app.ios.associatedDomains?.includes("applinks:employee.acpenterprise.com") && entitlements.includes("applinks:employee.acpenterprise.com"), "iOS Universal Link configuration is required");
requireConfig(app.android.intentFilters?.some((filter: { data?: { host?: string; pathPrefix?: string }[] }) => filter.data?.some((item) => item.host === "employee.acpenterprise.com" && item.pathPrefix === "/activate")), "Android activation App Link is required");
requireConfig(manifest.includes('android:host="employee.acpenterprise.com"') && manifest.includes('android:pathPrefix="/activate"'), "Native Android App Link must match Expo");
requireConfig(manifest.includes('android:usesCleartextTraffic="false"'), "Android release transport must reject cleartext traffic");
for (const permission of ["READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE", "SYSTEM_ALERT_WINDOW"]) requireConfig(!manifest.includes(permission), `Release manifest must not request ${permission}`);
const secureStore = app.plugins?.find((plugin: unknown) => Array.isArray(plugin) && plugin[0] === "expo-secure-store");
requireConfig(secureStore?.[1]?.configureAndroidBackup === true && secureStore?.[1]?.faceIDPermission === false, "SecureStore native configuration must be explicit");

console.log("ACP Employee beta configuration is structurally valid and Production remains inactive.");
