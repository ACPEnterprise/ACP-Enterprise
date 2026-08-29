import Constants from "expo-constants";
import { z } from "zod";

const schema = z.object({
  environment: z.enum(["development", "preview", "production"]),
  apiBaseUrl: z.string().url().refine((url) => !url.includes("example.invalid"), "API base URL is not activated"),
  compatibilityVersion: z.string().min(1),
});

const previewApiBaseUrl = "https://preview.allcountyhomeservices.com";

export type AppEnvironment = z.infer<typeof schema>;

export function readEnvironment(source: Record<string, unknown> = Constants.expoConfig?.extra ?? {}): AppEnvironment {
  const environment = process.env.EXPO_PUBLIC_APP_ENV ?? source.environment;
  const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL ?? source.apiBaseUrl;
  const parsed = schema.parse({ environment, apiBaseUrl, compatibilityVersion: source.compatibilityVersion });
  if (parsed.environment === "preview" && parsed.apiBaseUrl !== previewApiBaseUrl) {
    throw new Error("Preview builds must use the authorized ACP Preview API");
  }
  if (parsed.environment === "production") {
    const activated = process.env.EXPO_PUBLIC_PRODUCTION_ACTIVATED ?? source.productionActivated;
    if (activated !== "true" && activated !== true) throw new Error("Production is inactive");
    if (!parsed.apiBaseUrl.startsWith("https://")) throw new Error("Production requires HTTPS");
  }
  return parsed;
}
