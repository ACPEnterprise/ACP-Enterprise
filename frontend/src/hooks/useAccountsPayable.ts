import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/accountsPayable";
export const apKeys = { all: ["accounts-payable"] as const, aging: (asOf: string) => ["accounts-payable", "aging", asOf] as const };
export const useAPAging = (asOf: string, enabled = true) => useQuery({ queryKey: apKeys.aging(asOf), queryFn: () => api.getAPAging(asOf), enabled });
export function useAPMutations() { const client = useQueryClient(); return { createVendor: useMutation({ mutationFn: api.createAccountingVendor, onSuccess: () => void client.invalidateQueries({ queryKey: apKeys.all }) }) }; }
