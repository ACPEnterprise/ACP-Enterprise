import Constants from "expo-constants";
import type { AppEnvironment } from "../config/environment";

export type SafeBuildIdentity = Readonly<{
  product: "ACP Employee";
  version: string;
  build: string;
  environment: AppEnvironment["environment"];
  channel: "development" | "preview" | "production";
  compatibilityVersion: string;
}>;

export function currentAppVersion(): string { return Constants.expoConfig?.version ?? "unknown"; }

export function safeBuildIdentity(environment: AppEnvironment): SafeBuildIdentity {
  const config = Constants.expoConfig;
  return {
    product: "ACP Employee",
    version: currentAppVersion(),
    build: config?.ios?.buildNumber ?? String(config?.android?.versionCode ?? "unknown"),
    environment: environment.environment,
    channel: environment.environment,
    compatibilityVersion: environment.compatibilityVersion,
  };
}
