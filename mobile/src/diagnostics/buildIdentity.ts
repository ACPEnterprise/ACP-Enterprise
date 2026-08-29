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

export function safeBuildIdentity(environment: AppEnvironment): SafeBuildIdentity {
  const config = Constants.expoConfig;
  return {
    product: "ACP Employee",
    version: config?.version ?? "unknown",
    build: config?.ios?.buildNumber ?? String(config?.android?.versionCode ?? "unknown"),
    environment: environment.environment,
    channel: environment.environment,
    compatibilityVersion: environment.compatibilityVersion,
  };
}
