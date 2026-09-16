import { useQuery } from "@tanstack/react-query";
import {
  getQboAccountingEvidence,
  getQboSourceBackedArSummary,
  getQboSourceBackedProfitAndLoss,
} from "../api/qboAccountingEvidence";

export const useQboSourceBackedArSummary = (
  reportDate: string,
  enabled = true,
) =>
  useQuery({
    queryKey: ["accounting", "source-evidence", "qbo", "aged-receivables", reportDate],
    queryFn: () => getQboSourceBackedArSummary(reportDate),
    enabled: enabled && Boolean(reportDate),
    retry: false,
  });

export const useQboAccountingEvidence = (
  basis: "cash" | "accrual",
  enabled = true,
) =>
  useQuery({
    queryKey: ["accounting", "source-evidence", "qbo", basis],
    queryFn: () => getQboAccountingEvidence(basis),
    enabled,
    retry: false,
  });

export const useQboSourceBackedProfitAndLoss = (
  request: {
    startDate: string;
    endDate: string;
    basis: "cash" | "accrual";
  },
  enabled = true,
) =>
  useQuery({
    queryKey: [
      "accounting",
      "source-evidence",
      "qbo",
      "profit-and-loss",
      request,
    ],
    queryFn: () => getQboSourceBackedProfitAndLoss(request),
    enabled,
    retry: false,
  });
