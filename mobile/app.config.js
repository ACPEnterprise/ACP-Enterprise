const previewApi = "https://preview.allcountyhomeservices.com";
const inactiveProductionApi = "https://production-api.example.invalid";
const environment = process.env.EXPO_PUBLIC_APP_ENV ?? "development";
let releaseEnvironment;

if (environment === "development") {
  releaseEnvironment = { environment, apiBaseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8000", productionActivated: false };
} else if (environment === "preview") {
  const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL ?? previewApi;
  if (apiBaseUrl !== previewApi) throw new Error("Preview native configuration must use the authorized ACP Preview API");
  releaseEnvironment = { environment, apiBaseUrl, productionActivated: false };
} else if (environment === "production") {
  if (process.env.EXPO_PUBLIC_PRODUCTION_ACTIVATED === "true") throw new Error("Production native configuration is not authorized in this release packet");
  releaseEnvironment = { environment, apiBaseUrl: inactiveProductionApi, productionActivated: false };
} else {
  throw new Error(`Unsupported ACP Employee environment: ${environment}`);
}

module.exports = ({ config }) => ({
  ...config,
  extra: { ...config.extra, ...releaseEnvironment },
});
