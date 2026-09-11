import { useQuery } from "@tanstack/react-query";
import { getQboAccountingEvidence } from "../api/qboAccountingEvidence";

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
