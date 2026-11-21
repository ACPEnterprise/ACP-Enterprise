import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { acceptAccessAgreement, getCurrentAccessAgreement } from "../api/accessAgreements";

export function useCurrentAccessAgreement(companyId?: string, enabled = true) {
  return useQuery({
    queryKey: ["access-agreement", companyId ?? "unselected", "current"],
    queryFn: getCurrentAccessAgreement,
    enabled: enabled && Boolean(companyId),
    retry: false,
  });
}

export function useAcceptAccessAgreement() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: acceptAccessAgreement,
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["access-agreement"] });
    },
  });
}
