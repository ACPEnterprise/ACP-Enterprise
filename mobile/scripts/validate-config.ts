import { readFileSync } from "node:fs";
const app = JSON.parse(readFileSync(new URL("../app.json", import.meta.url), "utf8"));
if (!app.expo.ios?.bundleIdentifier || !app.expo.android?.package) throw new Error("Both native application identifiers are required");
if (app.expo.updates?.enabled !== false) throw new Error("Remote production updates must remain inactive in APP.1");
if (!app.expo.ios.associatedDomains?.length || !app.expo.android.intentFilters?.length) throw new Error("Native link configuration is required");
console.log("iOS and Android application configuration is structurally valid.");
