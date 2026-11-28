import { useQuery } from "@tanstack/react-query";
import {
  getQboAccountingEvidence,
  getQboHistoricalCatalog,
  getQboHistoricalReport,
  getQboSourceBackedArSummary,
  getQboSourceBackedProfitAndLoss,
  searchQboHistoricalRecords,
} from "../api/qboAccountingEvidence";
import type {
  QboHistoricalKind,
  QboHistoricalReportType,
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

export const useQboHistoricalCatalog = (enabled = true) =>
  useQuery({
    queryKey: ["accounting", "source-evidence", "qbo", "historical", "catalog"],
    queryFn: getQboHistoricalCatalog,
    enabled,
    retry: false,
  });

export const useQboHistoricalRecords = (
  request: {
    kind: QboHistoricalKind;
    query?: string;
    startDate?: string;
    endDate?: string;
  },
  enabled = true,
) =>
  useQuery({
    queryKey: [
      "accounting",
      "source-evidence",
      "qbo",
      "historical",
      "records",
      request,
    ],
    queryFn: () => searchQboHistoricalRecords(request),
    enabled,
    retry: false,
  });

export const useQboHistoricalReport = (
  request: {
    report: QboHistoricalReportType;
    startDate?: string;
    endDate?: string;
  },
  enabled = true,
) =>
  useQuery({
    queryKey: [
      "accounting",
      "source-evidence",
      "qbo",
      "historical",
      "report",
      request,
    ],
    queryFn: () => getQboHistoricalReport(request),
    enabled,
    retry: false,
  });
