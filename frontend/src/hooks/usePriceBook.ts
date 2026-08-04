import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/priceBook";

export const priceBookKeys = { all: ["price-book"] as const, catalog: (branch?: string) => ["price-book", "catalog", branch] as const };
export function usePriceBook(branch?: string, enabled = true) { return useQuery({ queryKey: priceBookKeys.catalog(branch), queryFn: () => api.getPriceBook(branch), enabled }); }
export function usePriceBookMutations() {
  const client = useQueryClient(); const refresh = () => client.invalidateQueries({ queryKey: priceBookKeys.all });
  return {
    category: useMutation({ mutationFn: api.createCategory, onSuccess: refresh }),
    tax: useMutation({ mutationFn: api.createTax, onSuccess: refresh }),
    item: useMutation({ mutationFn: api.createServiceItem, onSuccess: refresh }),
    version: useMutation({ mutationFn: ({ itemId, data }: { itemId: string; data: Parameters<typeof api.createPriceVersion>[1] }) => api.createPriceVersion(itemId, data), onSuccess: refresh }),
    activate: useMutation({ mutationFn: ({ id, version }: { id: string; version: number }) => api.activatePriceVersion(id, version), onSuccess: refresh }),
    optionGroup: useMutation({ mutationFn: api.createOptionGroup, onSuccess: refresh }),
    option: useMutation({ mutationFn: ({ groupId, data }: { groupId: string; data: Parameters<typeof api.addOption>[1] }) => api.addOption(groupId, data), onSuccess: refresh }),
  };
}
