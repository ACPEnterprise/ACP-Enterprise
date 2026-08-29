import { z } from "zod";
import type { ApiClient } from "./client";
import { capabilitiesFromPermissions } from "../permissions/capabilities";
const schema = z.object({ company_id: z.string(), active_branch_id: z.string().nullable(), permission_codes: z.array(z.string()) });
export async function getCapabilities(client: ApiClient) { return capabilitiesFromPermissions((await client.request("/api/v1/authorization/context", schema)).permission_codes); }
