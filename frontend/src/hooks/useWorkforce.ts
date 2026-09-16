import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  evaluateWorkforceEligibility,
  bindRealRosterEmployee,
  getEmployeeAdministration,
  getEmployeePasswordReset,
  getRealRosterReadiness,
  getWorkforceEmployee,
  listWorkforceEmployees,
  prepareEmployeeFieldReadiness,
  setEmployeeBranchGrant,
  setEmployeeMembershipStatus,
  setEmployeeRole,
  sendEmployeePasswordReset,
} from "../api/workforce";

export function useWorkforceDirectory() {
  return useQuery({ queryKey: ["workforce-directory"], queryFn: listWorkforceEmployees });
}

export function useRealRosterReadiness(canBind: boolean) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["real-workforce-roster"],
    queryFn: getRealRosterReadiness,
  });
  const bind = useMutation({
    mutationFn: ({ rosterKey, employeeId }: { rosterKey: string; employeeId: string }) =>
      bindRealRosterEmployee(rosterKey, employeeId),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["real-workforce-roster"] }),
        client.invalidateQueries({ queryKey: ["workforce-directory"] }),
      ]);
    },
  });
  const prepareFieldReadiness = useMutation({
    mutationFn: ({ employeeId, branchId, windowStartAt, windowEndAt }: {
      employeeId: string;
      branchId: string;
      windowStartAt: string;
      windowEndAt: string;
    }) => prepareEmployeeFieldReadiness(
      employeeId, branchId, windowStartAt, windowEndAt,
    ),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["real-workforce-roster"] }),
        client.invalidateQueries({ queryKey: ["workforce-directory"] }),
      ]);
    },
  });
  return { query, bind, prepareFieldReadiness, canBind };
}

export function useEmployeePasswordReset(userId: string | null, enabled: boolean) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["employee-password-reset", userId],
    queryFn: () => getEmployeePasswordReset(userId as string),
    enabled: enabled && Boolean(userId),
  });
  const mutation = useMutation({
    mutationFn: () => sendEmployeePasswordReset(userId as string),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["employee-password-reset", userId] });
    },
  });
  return { query, mutation };
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

export function useEmployeeAdministration(
  employeeId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["employee-administration", employeeId],
    queryFn: () => getEmployeeAdministration(employeeId as string),
    enabled: enabled && Boolean(employeeId),
  });
}

export function useEmployeeAccessMutation(employeeId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (
      command:
        | { type: "membership"; membershipId: string; status: "active" | "suspended" | "revoked" }
        | { type: "branch"; membershipId: string; branchId: string; enabled: boolean }
        | { type: "role"; membershipId: string; roleId: string; enabled: boolean },
    ) => {
      if (command.type === "membership")
        return setEmployeeMembershipStatus(command.membershipId, command.status);
      if (command.type === "branch")
        return setEmployeeBranchGrant(
          command.membershipId,
          command.branchId,
          command.enabled,
        );
      return setEmployeeRole(command.membershipId, command.roleId, command.enabled);
    },
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["employee-administration", employeeId] }),
        client.invalidateQueries({ queryKey: ["workforce-directory"] }),
      ]);
    },
  });
}
