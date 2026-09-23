import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  evaluateWorkforceEligibility,
  bindRealRosterEmployee,
  decideSourceCertification,
  getEmployeeAdministration,
  getEmployeePasswordReset,
  getEmployeeTimeline,
  getRealRosterReadiness,
  getSourceCertificationLedger,
  getWorkforceEmployee,
  listWorkforceEmployees,
  prepareEmployeeFieldReadiness,
  setEmployeeBranchGrant,
  setEmployeeMembershipStatus,
  setEmployeeRole,
  sendEmployeePasswordReset,
  setEmployeeAccessLock,
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
    mutationFn: ({ employeeId, branchId, windowStartAt, windowEndAt, reason }: {
      employeeId: string;
      branchId: string;
      windowStartAt: string;
      windowEndAt: string;
      reason: string;
    }) => prepareEmployeeFieldReadiness(
      employeeId, branchId, windowStartAt, windowEndAt, reason,
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

export function useSourceCertification(enabled: boolean) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["workforce-source-certifications"],
    queryFn: getSourceCertificationLedger,
    enabled,
  });
  const decide = useMutation({
    mutationFn: ({ sourceEmployeeId, ...input }: Parameters<typeof decideSourceCertification>[1] & { sourceEmployeeId: string }) =>
      decideSourceCertification(sourceEmployeeId, input),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["workforce-source-certifications"] }),
        client.invalidateQueries({ queryKey: ["real-workforce-roster"] }),
      ]);
    },
  });
  return { query, decide };
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

export function useEmployeeFieldReadiness(employeeId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      branchId: string;
      windowStartAt: string;
      windowEndAt: string;
      reason: string;
    }) =>
      prepareEmployeeFieldReadiness(
        employeeId as string,
        input.branchId,
        input.windowStartAt,
        input.windowEndAt,
        input.reason,
      ),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["workforce-employee", employeeId] }),
        client.invalidateQueries({ queryKey: ["workforce-directory"] }),
      ]);
    },
  });
}

export function useEmployeeTimeline(employeeId: string | null) {
  return useQuery({
    queryKey: ["employee-timeline", employeeId],
    queryFn: () => getEmployeeTimeline(employeeId as string),
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

export function useEmployeeAccessLock(employeeId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      locked: boolean;
      reason: string;
      expected_authorization_version: number;
    }) => setEmployeeAccessLock(employeeId as string, input),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["employee-administration", employeeId] }),
        client.invalidateQueries({ queryKey: ["workforce-directory"] }),
        client.invalidateQueries({ queryKey: ["employee-timeline", employeeId] }),
      ]);
    },
  });
}
