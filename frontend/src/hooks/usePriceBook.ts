import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/priceBook";

export const priceBookKeys = { all: ["price-book"] as const, catalog: (branch?: string) => ["price-book", "catalog", branch] as const };
export function usePriceBook(branch?: string, enabled = true, operator = false) { return useQuery({ queryKey: [...priceBookKeys.catalog(branch), operator ? "operator" : "reader"], queryFn: () => operator ? api.getOperatorPriceBook(branch) : api.getPriceBook(branch), enabled }); }
export function usePriceBookMutations() {
  const client = useQueryClient(); const refresh = () => client.invalidateQueries({ queryKey: priceBookKeys.all });
  return {
    category: useMutation({ mutationFn: api.createCategory, onSuccess: refresh }),
    updateCategory: useMutation({ mutationFn: ({ id, data }: { id: string; data: Parameters<typeof api.updateCategory>[1] }) => api.updateCategory(id, data), onSuccess: refresh }),
    tax: useMutation({ mutationFn: api.createTax, onSuccess: refresh }),
    updateTax: useMutation({ mutationFn: ({ id, data }: { id: string; data: Parameters<typeof api.updateTax>[1] }) => api.updateTax(id, data), onSuccess: refresh }),
    item: useMutation({ mutationFn: api.createServiceItem, onSuccess: refresh }),
    updateItem: useMutation({ mutationFn: ({ id, data }: { id: string; data: Parameters<typeof api.updateServiceItem>[1] }) => api.updateServiceItem(id, data), onSuccess: refresh }),
    version: useMutation({ mutationFn: ({ itemId, data }: { itemId: string; data: Parameters<typeof api.createPriceVersion>[1] }) => api.createPriceVersion(itemId, data), onSuccess: refresh }),
    updateVersion: useMutation({ mutationFn: ({ id, data }: { id: string; data: Parameters<typeof api.updatePriceVersion>[1] }) => api.updatePriceVersion(id, data), onSuccess: refresh }),
    activate: useMutation({ mutationFn: ({ id, version }: { id: string; version: number }) => api.activatePriceVersion(id, version), onSuccess: refresh }),
    transition: useMutation({ mutationFn: ({ id, version, action }: { id: string; version: number; action: "inactivate" | "archive" }) => api.transitionPriceVersion(id, version, action), onSuccess: refresh }),
    optionGroup: useMutation({ mutationFn: api.createOptionGroup, onSuccess: refresh }),
    option: useMutation({ mutationFn: ({ groupId, data }: { groupId: string; data: Parameters<typeof api.addOption>[1] }) => api.addOption(groupId, data), onSuccess: refresh }),
  };
}
