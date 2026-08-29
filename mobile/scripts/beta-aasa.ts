import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { generateAasa } from "../src/operations/betaContracts";

const teamId = process.env.APPLE_TEAM_ID;
if (!teamId) throw new Error("APPLE_TEAM_ID is required; AASA generation fails closed until Apple supplies the Team ID");
const output = resolve(process.argv[2] ?? "build/beta/apple-app-site-association");
mkdirSync(dirname(output), { recursive: true });
writeFileSync(output, generateAasa(teamId), { encoding: "utf8", mode: 0o644 });
console.info(`Generated AASA at ${output}; serve unchanged as application/json without redirect or authentication.`);
