import { useQuery } from "@tanstack/react-query";

import { useMutation } from "@tanstack/react-query";

import { evaluateWorkforceEligibility, getWorkforceEmployee, listWorkforceEmployees } from "../api/workforce";

export function useWorkforceDirectory() {
  return useQuery({ queryKey: ["workforce-directory"], queryFn: listWorkforceEmployees });
}

export function useWorkforceEligibility() {
  return useMutation({ mutationFn: evaluateWorkforceEligibility });
}

export function useWorkforceEmployee(employeeId: string | null) {
  return useQuery({
    queryKey: ["workforce-employee", employeeId],
    queryFn: () => getWorkforceEmployee(employeeId as string),
    enabled: Boolean(employeeId),
  });
}
