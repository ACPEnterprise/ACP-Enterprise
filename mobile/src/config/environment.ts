import Constants from "expo-constants";
import { z } from "zod";

const schema = z.object({
  environment: z.enum(["development", "preview", "production"]),
  apiBaseUrl: z.string().url().refine((url) => !url.includes("example.invalid"), "API base URL is not activated"),
  compatibilityVersion: z.string().min(1),
});

export type AppEnvironment = z.infer<typeof schema>;

export function readEnvironment(source: Record<string, unknown> = Constants.expoConfig?.extra ?? {}): AppEnvironment {
  const environment = process.env.EXPO_PUBLIC_APP_ENV ?? source.environment;
  const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL ?? source.apiBaseUrl;
  return schema.parse({ environment, apiBaseUrl, compatibilityVersion: source.compatibilityVersion });
}
