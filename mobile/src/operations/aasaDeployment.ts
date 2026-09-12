import { generateAasa } from "./betaContracts";

export type AasaResponseEvidence = {
  requestedUrl: string;
  responseUrl: string;
  status: number;
  contentType: string | null;
  cacheControl: string | null;
  body: string;
};

export const AASA_URL = "https://employee.acpenterprise.com/.well-known/apple-app-site-association";

export function validateAasaDeployment(teamId: string, evidence: AasaResponseEvidence): void {
  if (evidence.requestedUrl !== AASA_URL || evidence.responseUrl !== AASA_URL) throw new Error("AASA must be served from the exact HTTPS URL without redirect");
  if (evidence.status !== 200) throw new Error(`AASA returned HTTP ${evidence.status}`);
  if (!/^application\/json(?:\s*;|$)/i.test(evidence.contentType ?? "")) throw new Error("AASA Content-Type must be application/json");
  if (!/\b(public|private)\b/i.test(evidence.cacheControl ?? "")) throw new Error("AASA must declare an explicit bounded cache policy");
  if (evidence.body !== generateAasa(teamId)) throw new Error("AASA response bytes do not match the repository-generated contract");
}
