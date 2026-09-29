import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  applyQboSafeMajority,
  getQboApplicationLedger,
  getQboReviewQueue,
} from "../api/qboNativeApplication";

const ledgerKey = ["qbo-native-application"] as const;
const reviewKey = ["qbo-native-application", "review-queue"] as const;

export const useQboApplicationLedger = (enabled = true) =>
  useQuery({ queryKey: ledgerKey, queryFn: getQboApplicationLedger, enabled });

export const useQboReviewQueue = (enabled = true) =>
  useQuery({ queryKey: reviewKey, queryFn: getQboReviewQueue, enabled });

export const useApplyQboSafeMajority = () => {
  const client = useQueryClient();
  return useMutation({
    mutationFn: applyQboSafeMajority,
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ledgerKey }),
        client.invalidateQueries({ queryKey: reviewKey }),
      ]);
    },
  });
};
