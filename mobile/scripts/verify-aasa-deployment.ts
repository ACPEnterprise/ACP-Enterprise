import { AASA_URL, validateAasaDeployment } from "../src/operations/aasaDeployment";

const teamId = process.env.APPLE_TEAM_ID;
if (!teamId) throw new Error("APPLE_TEAM_ID is required; deployment verification fails closed");

const response = await fetch(AASA_URL, { redirect: "manual", headers: { Accept: "application/json" } });
validateAasaDeployment(teamId, {
  requestedUrl: AASA_URL,
  responseUrl: response.url,
  status: response.status,
  contentType: response.headers.get("content-type"),
  cacheControl: response.headers.get("cache-control"),
  body: await response.text(),
});
console.info(`Verified exact AASA bytes at ${AASA_URL}.`);
