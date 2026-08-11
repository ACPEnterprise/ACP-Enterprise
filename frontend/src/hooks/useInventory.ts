import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getInventoryOverview, postInventoryTransfer, releaseInventoryReservation } from "../api/inventory";

const inventoryKeys = { all: ["inventory"] as const, overview: (branch?: string) => ["inventory", "overview", branch] as const };

export function useInventory(branch?: string, enabled = true) {
  return useQuery({ queryKey: inventoryKeys.overview(branch), queryFn: () => getInventoryOverview(branch), enabled });
}

export function useInventoryMutations() {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: inventoryKeys.all });
  return {
    transfer: useMutation({ mutationFn: postInventoryTransfer, onSuccess: refresh }),
    release: useMutation({ mutationFn: ({ id, version }: { id: string; version: number }) => releaseInventoryReservation(id, version), onSuccess: refresh }),
  };
}
