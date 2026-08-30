import { useQuery } from "@tanstack/react-query";

import { getWorkforceEmployee, listWorkforceEmployees } from "../api/workforce";

export function useWorkforceDirectory() {
  return useQuery({ queryKey: ["workforce-directory"], queryFn: listWorkforceEmployees });
}

export function useWorkforceEmployee(employeeId: string | null) {
  return useQuery({
    queryKey: ["workforce-employee", employeeId],
    queryFn: () => getWorkforceEmployee(employeeId as string),
    enabled: Boolean(employeeId),
  });
}
