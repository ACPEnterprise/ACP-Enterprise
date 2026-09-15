import { useQuery } from "@tanstack/react-query";
import {
  getQboAccountingEvidence,
  getQboSourceBackedProfitAndLoss,
} from "../api/qboAccountingEvidence";

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
