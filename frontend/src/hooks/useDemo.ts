import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getDemoScenarios, resetDemo, sendDemoFeedback } from "../api/demo";

export const useDemoScenarios = (enabled = true, companyId?: string) => useQuery({
  queryKey: ["sales-demo", companyId ?? "unselected", "scenarios"],
  queryFn: getDemoScenarios,
  enabled,
});
export function useResetDemo() {
  const client = useQueryClient();
  return useMutation({ mutationFn: resetDemo, onSuccess: async () => { await client.invalidateQueries(); } });
}
export const useDemoFeedback = () => useMutation({ mutationFn: sendDemoFeedback });
