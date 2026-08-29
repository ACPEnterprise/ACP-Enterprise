import { apiClient } from "./client";
import type {
  EvaluateProcurementMatchInput,
  ProcurementMatch,
  ResolveProcurementMatchInput,
  VendorPerformanceReport,
} from "../types/procurementMatching";

const root = "/api/v1/procurement-matching";

export const getProcurementMatch = async (matchId: string): Promise<ProcurementMatch> =>
  (await apiClient.get<ProcurementMatch>(`${root}/matches/${matchId}`)).data;

export const evaluateProcurementMatch = async (
  input: EvaluateProcurementMatchInput,
): Promise<ProcurementMatch> =>
  (await apiClient.post<ProcurementMatch>(`${root}/matches`, input)).data;

export const resolveProcurementMatch = async ({
  matchId,
  exceptionId,
  ...input
}: ResolveProcurementMatchInput): Promise<ProcurementMatch> =>
  (
    await apiClient.post<ProcurementMatch>(
      `${root}/matches/${matchId}/exceptions/${exceptionId}/resolve`,
      input,
    )
  ).data;

export const getVendorPerformance = async (
  evaluatedAt: string,
  branchId?: string,
): Promise<VendorPerformanceReport> =>
  (
    await apiClient.get<VendorPerformanceReport>(`${root}/vendor-performance`, {
      params: { evaluated_at: evaluatedAt, branch_id: branchId || undefined },
    })
  ).data;
