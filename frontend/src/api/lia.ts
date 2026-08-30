import { apiClient } from "./client";
import type { LiaReadiness, LiaResponse } from "../types/lia";

export async function getLiaReadiness(): Promise<LiaReadiness> {
  return (await apiClient.get<LiaReadiness>("/api/v1/lia/readiness")).data;
}

export async function getOwnerBriefing(): Promise<LiaResponse> {
  return (await apiClient.get<LiaResponse>("/api/v1/lia/briefing")).data;
}

export async function askLia(input: {
  question: string;
  conversation_id?: string;
  context?: { domain?: string; entity_id?: string };
}): Promise<LiaResponse> {
  return (await apiClient.post<LiaResponse>("/api/v1/lia/ask", input)).data;
}
