import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getDemoScenarios, getDemoSignals, resetDemo, sendDemoFeedback } from "../api/demo";

export const useDemoScenarios = () => useQuery({ queryKey: ["sales-demo", "scenarios"], queryFn: getDemoScenarios });
export const useDemoSignals = () => useQuery({ queryKey: ["sales-demo", "signals"], queryFn: getDemoSignals });
export function useResetDemo() {
  const client = useQueryClient();
  return useMutation({ mutationFn: resetDemo, onSuccess: async () => { await client.invalidateQueries(); } });
}
export const useDemoFeedback = () => useMutation({ mutationFn: sendDemoFeedback });

