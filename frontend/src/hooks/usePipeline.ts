import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createLead, listLeads } from "../api/pipeline";

export function useLeads(view: string, enabled = true) {
  return useQuery({
    queryKey: ["pipeline", view],
    queryFn: () => listLeads(view),
    enabled,
  });
}

export function useCreateLead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: createLead,
    onSuccess: () => client.invalidateQueries({ queryKey: ["pipeline"] }),
  });
}

