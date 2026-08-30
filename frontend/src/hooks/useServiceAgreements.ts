import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/serviceAgreements";
const key = ["service-agreements"] as const;
export function useAgreementWorkspace() {
  return useQuery({ queryKey: key, queryFn: api.getAgreementWorkspace });
}
export function useAgreementPlans() {
  return useQuery({
    queryKey: [...key, "plans"],
    queryFn: api.listAgreementPlans,
  });
}
export function useAgreementMutations() {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: key });
  return {
    createPlan: useMutation({
      mutationFn: api.createAgreementPlan,
      onSuccess: refresh,
    }),
    activatePlan: useMutation({
      mutationFn: api.activateAgreementPlan,
      onSuccess: refresh,
    }),
    enroll: useMutation({
      mutationFn: api.enrollAgreement,
      onSuccess: refresh,
    }),
    transition: useMutation({
      mutationFn: ({
        id,
        action,
        input,
      }: {
        id: string;
        action: string;
        input: Record<string, unknown>;
      }) => api.transitionAgreement(id, action, input),
      onSuccess: refresh,
    }),
    generate: useMutation({
      mutationFn: api.generateEntitlements,
      onSuccess: refresh,
    }),
  };
}
