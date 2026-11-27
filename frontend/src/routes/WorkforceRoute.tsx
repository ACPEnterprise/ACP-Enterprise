import { useEffect, useMemo, useState } from "react";
import { Award, Languages, Search, ShieldCheck, UserRoundCheck, UsersRound } from "lucide-react";
import { Link, useSearchParams } from "react-router";

import { getOperatorApiError } from "../api/errors";
import type { AdminEmployeeTimecard } from "../api/timekeeping";
import type { EmployeePermissionExplanation } from "../api/workforce";
import { useAuth } from "../auth";
import { RealRosterActivationConsole } from "../components/workforce/RealRosterActivationConsole";
import { ReadinessBlockers } from "../components/workforce/ReadinessBlockers";
import { useEmployeeAccessLock, useEmployeeAccessMutation, useEmployeeAdministration, useEmployeeDeactivation, useEmployeeFunctionalAccess, useEmployeePasswordReset, useEmployeePermissionUpdate, useEmployeeProfileUpdate, useEmployeeTimeline, useHistoricalWorkforceIdentities, useSourceCertification, useWorkforceDirectory, useWorkforceEligibility, useWorkforceEmployee } from "../hooks/useWorkforce";
import { useAdminTimecardOperations, useAdminTimecardReview, useApproveTimeEntry, usePayPeriods, useTimeCorrection } from "../hooks/useWorkdayTime";
import { useRoles } from "../features/administration/hooks";
import { listPermissions } from "../features/administration/api";
import { Alert, Badge, Button, Card, ConfirmationDialog, Input, Select, Spinner } from "../ui";

function Readiness({ state }: { state: "READY" | "BLOCKED" | "INSUFFICIENT_EVIDENCE" }) {
  return <Badge variant={state === "READY" ? "success" : "danger"}>{state === "READY" ? "EMPLOYEE READY" : "EMPLOYEE BLOCKED"}</Badge>;
}

function OwnerAttention({ state }: { state: "READY" | "BLOCKED" | "INSUFFICIENT_EVIDENCE" }) {
  return <Badge variant={state === "READY" ? "success" : "warning"}>{state === "READY" ? "READY" : "ATTENTION REQUIRED"}</Badge>;
}

function workforceGroup(employee: { job_title: string | null; employee_type: string }) {
  const role = `${employee.job_title ?? ""} ${employee.employee_type}`.toUpperCase();
  if (role.includes("ADMIN") || role.includes("OWNER")) return "Company administrators / owners";
  if (role.includes("FIELD MANAGER")) return "Field managers";
  if (role.includes("OFFICE") || role.includes("MANAGER")) return "Office / management";
  if (role.includes("TECHNICIAN") || role.includes("TECH")) return "Technicians";
  if (role.includes("HELPER")) return "Helpers";
  return "Other explicit roles";
}

function visiblePosition(employee: { job_title: string | null; employee_type: string }) {
  const title = (employee.job_title ?? "").trim();
  const normalized = title.toLowerCase();
  if (normalized.includes("technician") || normalized.includes("field tech")) return "Technician";
  if (normalized.includes("helper")) return "Helper";
  if (normalized.includes("field manager")) return "Field Manager";
  if (normalized.includes("office manager")) return "Office Manager";
  if (normalized.includes("administrator") || normalized === "owner") return "Owner / Administrator";
  return title || employee.employee_type.replaceAll("_", " ");
}

const ACCESS_PROFILES = [
  { label: "Company Administrator", code: "COMPANY_ADMINISTRATOR", aliases: ["COMPANY_ADMINISTRATOR", "OWNER"] },
  { label: "Office Manager", code: "OFFICE_MANAGER", aliases: ["OFFICE_MANAGER"] },
  { label: "Field Manager", code: "FIELD_MANAGER", aliases: ["FIELD_MANAGER"] },
  { label: "Technician", code: "TECHNICIAN", aliases: ["TECHNICIAN"] },
  { label: "Helper", code: "HELPER", aliases: ["HELPER"] },
] as const;

const PERMISSION_GROUPS = [
  { label: "Customers", area: "Customers", options: [{ label: "View", code: "COMPANY_CUSTOMER_READ" }, { label: "Create / Edit", code: "COMPANY_CUSTOMER_MANAGE" }] },
  { label: "Estimates", area: "Estimates", options: [{ label: "View", code: "COMPANY_ESTIMATE_READ" }, { label: "Create / Edit", code: "COMPANY_ESTIMATE_MANAGE" }] },
  { label: "Jobs", area: "Jobs", options: [{ label: "View assigned", code: "COMPANY_JOB_READ" }, { label: "Update", code: "COMPANY_JOB_MANAGE" }, { label: "Complete work", code: "COMPANY_JOB_EXECUTE" }] },
  { label: "Scheduling", area: "Scheduling", options: [{ label: "View schedule", code: "COMPANY_SCHEDULING_READ" }, { label: "Schedule others", code: "COMPANY_SCHEDULING_MANAGE" }] },
  { label: "Dispatch", area: "Dispatch", options: [{ label: "View assigned", code: "COMPANY_DISPATCH_READ" }, { label: "Dispatch technicians", code: "COMPANY_DISPATCH_MANAGE" }] },
  { label: "Invoices", area: "Invoices", options: [{ label: "View", code: "COMPANY_INVOICE_READ" }, { label: "Create / Edit", code: "COMPANY_INVOICE_MANAGE" }, { label: "Issue", code: "COMPANY_INVOICE_ISSUE" }, { label: "Adjust", code: "COMPANY_INVOICE_ADJUST" }] },
  { label: "Employees", area: "Workforce", options: [{ label: "View", code: "COMPANY_WORKFORCE_READ" }, { label: "Add / Edit", code: "COMPANY_WORKFORCE_MANAGE" }, { label: "Capability setup", code: "COMPANY_WORKFORCE_CAPABILITY_MANAGE" }] },
  { label: "Accounting", area: "Accounting", options: [{ label: "View", code: "COMPANY_ACCOUNTING_READ" }, { label: "Post journals", code: "COMPANY_ACCOUNTING_JOURNAL_POST" }, { label: "Reconcile", code: "COMPANY_ACCOUNTING_RECONCILE" }] },
  { label: "Payroll", area: "Payroll", options: [{ label: "View own", code: "COMPANY_PAYROLL_STATEMENT_OWN_READ" }, { label: "Review workforce", code: "COMPANY_PAYROLL_REPORTING_READ" }] },
  { label: "Inventory", area: "Inventory", options: [{ label: "View", code: "COMPANY_INVENTORY_READ" }, { label: "Use materials", code: "COMPANY_INVENTORY_MOVE" }, { label: "Adjust inventory", code: "COMPANY_INVENTORY_ADJUST" }] },
  { label: "LIA / Beacon / Luminary", area: "Intelligence", options: [{ label: "Use", code: "COMPANY_BEACON_REVIEW" }, { label: "Management actions", code: "COMPANY_BEACON_ASSIGN" }] },
] as const;

function weeklyTimecardSummaries(employee: AdminEmployeeTimecard, periodStart: string) {
  const start = Date.parse(`${periodStart}T00:00:00Z`);
  const weeks = new Map<number, { supported: number; accepted: number; needsReview: boolean }>();
  for (const day of employee.days) {
    const week = Math.max(0, Math.floor((Date.parse(`${day.work_date}T00:00:00Z`) - start) / 604_800_000));
    const summary = weeks.get(week) ?? { supported: 0, accepted: 0, needsReview: false };
    summary.supported += day.total_supported_minutes;
    summary.accepted += day.review_state === "ACCEPTED" ? day.total_supported_minutes : 0;
    summary.needsReview ||= day.review_state === "NEEDS_REVIEW";
    weeks.set(week, summary);
  }
  return [...weeks.entries()].sort(([left], [right]) => left - right);
}

export function WorkforceRoute() {
  const [searchParams, setSearchParams] = useSearchParams();
  const linkedEmployeeId = searchParams.get("employee");
  const { activeCompany, permissionCodes = [] } = useAuth();
  const canAdministerEmployees = permissionCodes.includes("COMPANY_WORKFORCE_MANAGE") && permissionCodes.includes("COMPANY_MEMBERSHIP_READ") && permissionCodes.includes("COMPANY_ROLE_READ");
  const roles = useRoles(canAdministerEmployees);
  const directory = useWorkforceDirectory();
  const historicalDirectory = useHistoricalWorkforceIdentities?.() ?? { data: undefined };
  const canCertifySources = permissionCodes.includes("COMPANY_WORKFORCE_CERTIFICATION_MANAGE");
  const sourceCertifications = useSourceCertification(canCertifySources);
  const [sourceEmployeeSelections, setSourceEmployeeSelections] = useState<Record<string, string>>({});
  const [sourceReasons, setSourceReasons] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState<string | null>(linkedEmployeeId);
  const [search, setSearch] = useState("");
  const [branchFilter, setBranchFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("active");
  const [readinessFilter, setReadinessFilter] = useState("");
  const [viewMode, setViewMode] = useState<"list" | "org-chart">("list");
  const [detailTab, setDetailTab] = useState<"overview" | "access" | "time" | "payroll" | "history">("overview");
  const [editingEmployee, setEditingEmployee] = useState<string | null>(null);
  const [editPhone, setEditPhone] = useState("");
  const [editJobTitle, setEditJobTitle] = useState("");
  const [editBranchId, setEditBranchId] = useState("");
  const [deactivationReason, setDeactivationReason] = useState("");
  const [deactivationDate, setDeactivationDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [confirmDeactivation, setConfirmDeactivation] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const [permissionDrafts, setPermissionDrafts] = useState<Record<string, string[]>>({});
  const [permissionMessage, setPermissionMessage] = useState<string | null>(null);
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [permissionPresetPending, setPermissionPresetPending] = useState(false);
  const [pendingPermissionNavigation, setPendingPermissionNavigation] = useState<(() => void) | null>(null);
  const nativeSelected = selected?.startsWith("historical:") ? null : selected;
  const selectedHistorical = historicalDirectory.data?.items.find((item) => `historical:${item.id}` === selected);
  const detail = useWorkforceEmployee(nativeSelected);
  const timeline = useEmployeeTimeline(nativeSelected);
  const administration = useEmployeeAdministration(nativeSelected, canAdministerEmployees);
  const permissionUpdate = useEmployeePermissionUpdate(selected);
  const canAdministerIdentity = permissionCodes.includes("COMPANY_ADMINISTER");
  const functionalAccess = useEmployeeFunctionalAccess(nativeSelected, canAdministerIdentity);
  const [functionalArea, setFunctionalArea] = useState("FIELD_OPERATIONS");
  const [functionalLevel, setFunctionalLevel] = useState("TECHNICIAN");
  const [functionalEffective, setFunctionalEffective] = useState("");
  const [functionalExpires, setFunctionalExpires] = useState("");
  const [functionalReason, setFunctionalReason] = useState("");
  const passwordReset = useEmployeePasswordReset(
    administration.data?.user_id ?? null,
    canAdministerIdentity && administration.data?.access_status === "ACTIVE",
  );
  const [confirmPasswordReset, setConfirmPasswordReset] = useState(false);
  const [confirmAccessLock, setConfirmAccessLock] = useState(false);
  const [accessLockReason, setAccessLockReason] = useState("");
  const accessLock = useEmployeeAccessLock(nativeSelected);
  const profileUpdate = useEmployeeProfileUpdate(nativeSelected);
  const deactivation = useEmployeeDeactivation(nativeSelected);
  const accessMutation = useEmployeeAccessMutation(nativeSelected);
  const canManageMembership = permissionCodes.includes("COMPANY_MEMBERSHIP_MANAGE");
  const canManageBranches = permissionCodes.includes("COMPANY_BRANCH_ACCESS_MANAGE");
  const [selectedBranchGrant, setSelectedBranchGrant] = useState("");
  const eligibility = useWorkforceEligibility();
  const canReviewTime = permissionCodes.includes("COMPANY_TIMEKEEPING_ADMIN_READ");
  const timeReview = useAdminTimecardReview(canReviewTime);
  const canApproveTime = permissionCodes.includes("COMPANY_TIMEKEEPING_APPROVE");
  const timeApproval = useApproveTimeEntry();
  const [pendingTimeApproval, setPendingTimeApproval] = useState<{
    revisionId: string;
    employeeName: string;
    workDate: string;
  } | null>(null);
  const canCorrectTime = permissionCodes.includes("COMPANY_TIMEKEEPING_CORRECT");
  const timeCorrection = useTimeCorrection();
  const [correctionRevision, setCorrectionRevision] = useState("");
  const [correctionKind, setCorrectionKind] = useState<"missing_clock_out" | "incorrect_job" | "missing_interval" | "overlapping_intervals" | "incorrect_start" | "incorrect_stop">("missing_clock_out");
  const [correctionStart, setCorrectionStart] = useState("");
  const [correctionEnd, setCorrectionEnd] = useState("");
  const [correctionReason, setCorrectionReason] = useState("");
  const payPeriods = usePayPeriods(canReviewTime);
  const [selectedPayPeriodId, setSelectedPayPeriodId] = useState(searchParams.get("period") ?? "");
  const effectivePayPeriodId = selectedPayPeriodId || timeReview.data?.pay_period?.id || payPeriods.data?.[0]?.id || null;
  const timecards = useAdminTimecardOperations(effectivePayPeriodId, canReviewTime);
  const [branchId, setBranchId] = useState(() => activeCompany?.default_branch_id ?? activeCompany?.branches?.[0]?.id ?? "");
  const [windowStart, setWindowStart] = useState("");
  const [windowEnd, setWindowEnd] = useState("");
  const selectPayPeriod = (payPeriodId: string) => {
    setSelectedPayPeriodId(payPeriodId);
    const next = new URLSearchParams(searchParams);
    if (payPeriodId) next.set("period", payPeriodId);
    else next.delete("period");
    setSearchParams(next, { replace: true });
  };
  const [capabilities, setCapabilities] = useState("");
  const [languages, setLanguages] = useState("");
  const administrationPermissions = administration.data?.permissions;
  const permissionAreas = useMemo(() => {
    const groups: Record<string, EmployeePermissionExplanation[]> = {};
    for (const permission of administrationPermissions ?? []) {
      (groups[permission.business_area] ??= []).push(permission);
    }
    return groups;
  }, [administrationPermissions]);
  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (directory.data ?? []).filter((item) => {
      const statusMatches = !statusFilter
        || (statusFilter === "former"
          ? ["inactive", "leave", "terminated"].includes(item.employee_status)
          : item.employee_status === statusFilter);
      return (!query || [item.display_name, item.employee_number, item.job_title ?? "", ...item.capability_codes, ...item.language_codes].some((value) => value.toLowerCase().includes(query)))
        && (!branchFilter || item.home_branch_id === branchFilter)
        && statusMatches
        && (!readinessFilter || item.readiness_state === readinessFilter);
    });
  }, [branchFilter, directory.data, readinessFilter, search, statusFilter]);
  const filteredHistorical = useMemo(() => {
    if (statusFilter === "active") return [];
    const query = search.trim().toLowerCase();
    return (historicalDirectory.data?.items ?? []).filter((item) =>
      (!query || [item.display_name, item.source_identity, item.source_system, item.source_status ?? "", item.lifecycle_state].some((value) => value.toLowerCase().includes(query)))
      && (!readinessFilter || readinessFilter === "INSUFFICIENT_EVIDENCE"),
    );
  }, [historicalDirectory.data, readinessFilter, search, statusFilter]);
  const morningReview = useMemo(
    () => ({
      total: directory.data?.length ?? 0,
      inactive: (directory.data ?? []).filter((item) => item.employee_status !== "active").length,
      missingProfile: (directory.data ?? []).filter((item) => !item.profile_id).length,
      needsAttention: (directory.data ?? []).filter((item) => item.readiness_state !== "READY").length,
    }),
    [directory.data],
  );
  const branchName = (branchId: string | null) =>
    activeCompany?.branches?.find((branch) => branch.id === branchId)?.name ??
    (branchId ? "Authorized Branch" : "Company-wide / unassigned");
  const openEmployee = (employeeId: string) => {
    const navigate = () => {
      setSelected(employeeId);
      setDetailTab("overview");
      setSelectedProfile(null);
      setPermissionMessage(null);
      setPermissionError(null);
      const next = new URLSearchParams(searchParams);
      next.set("employee", employeeId);
      setSearchParams(next, { replace: true });
    };
    if (permissionDraftDirty) setPendingPermissionNavigation(() => navigate);
    else navigate();
  };
  const closeEmployee = () => {
    const navigate = () => {
      setSelected(null);
      setDetailTab("overview");
      setSelectedProfile(null);
      setPermissionMessage(null);
      setPermissionError(null);
      const next = new URLSearchParams(searchParams);
      next.delete("employee");
      setSearchParams(next, { replace: true });
    };
    if (permissionDraftDirty) setPendingPermissionNavigation(() => navigate);
    else navigate();
  };
  const inferredProfile = administration.data?.role_codes
    .map((roleCode) => ACCESS_PROFILES.find((profile) => profile.aliases.includes(roleCode as never)))
    .find(Boolean)?.code ?? null;
  const activeProfile = selectedProfile ?? inferredProfile;
  const savedPermissionCodes = useMemo(
    () => new Set((administration.data?.permissions ?? []).filter((permission) => permission.authority !== "DENIED").map((permission) => permission.code)),
    [administration.data?.permissions],
  );
  const draftPermissionCodes = selected && permissionDrafts[selected]
    ? new Set(permissionDrafts[selected])
    : savedPermissionCodes;
  const permissionDraftDirty = Boolean(selected && permissionDrafts[selected]
    && [...draftPermissionCodes].sort().join("|") !== [...savedPermissionCodes].sort().join("|"));
  useEffect(() => {
    if (!permissionDraftDirty) return undefined;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "You have unsaved permission changes.";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [permissionDraftDirty]);
  const setPermissionDraft = (codes: Set<string>) => {
    if (!selected) return;
    setPermissionDrafts((current) => ({ ...current, [selected]: [...codes].sort() }));
    setPermissionMessage(null);
    setPermissionError(null);
  };
  const applyAccessProfile = async (profileCode: string) => {
    setSelectedProfile(profileCode);
    if (profileCode === "CUSTOM") return;
    const profile = ACCESS_PROFILES.find((item) => item.code === profileCode);
    const targetRole = roles.data?.find((role) => profile?.aliases.some((alias) => alias === role.code));
    if (!targetRole) return;
    setPermissionPresetPending(true);
    try {
      const catalog = await listPermissions(targetRole.id);
      setPermissionDraft(new Set(catalog.filter((permission) => permission.assigned).map((permission) => permission.code)));
    } catch {
      setPermissionError("The selected Access Profile could not be loaded. Your saved permissions are unchanged.");
    } finally {
      setPermissionPresetPending(false);
    }
  };
  const savePermissionDraft = () => {
    if (!selected || !administration.data?.authorization_version || !activeProfile) return;
    setPermissionMessage(null);
    setPermissionError(null);
    permissionUpdate.mutate(
      {
        access_profile: activeProfile,
        permission_codes: [...draftPermissionCodes].sort(),
        expected_authorization_version: administration.data.authorization_version,
      },
      {
        onSuccess: () => {
          setPermissionDrafts((current) => {
            const next = { ...current };
            delete next[selected];
            return next;
          });
          setPermissionMessage("Permissions updated");
          const navigate = pendingPermissionNavigation;
          setPendingPermissionNavigation(null);
          navigate?.();
        },
        onError: () => setPermissionError("Permissions could not be saved. Your draft remains available; refresh and retry if another administrator changed access."),
      },
    );
  };
  const cancelPermissionDraft = () => {
    if (!selected) return;
    setPermissionDrafts((current) => {
      const next = { ...current };
      delete next[selected];
      return next;
    });
    setSelectedProfile(null);
    setPermissionMessage("Draft changes discarded");
    setPermissionError(null);
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-action-primary">Team</p>
          <h2 className="mt-1 text-2xl font-bold sm:text-3xl">Employees &amp; Time</h2>
          <p className="mt-2 text-content-muted">Employee readiness, access, accepted worked time, and Payroll-period review in one office workflow.</p>
        </div>
        {permissionCodes.includes("COMPANY_IDENTITY_ONBOARDING_MANAGE") && (
          <Link className="rounded-lg bg-action-primary px-4 py-2 font-semibold text-white" to="/administration/identity-onboarding">
            Add Employee
          </Link>
        )}
      </header>
      <nav aria-label="Team workspace" className="flex flex-wrap gap-2 rounded-xl border border-stroke bg-surface p-2">
        <a className="rounded-lg bg-action-primary px-4 py-2 font-semibold text-white" href="#employee-roster">Employees</a>
        {canReviewTime && <a className="rounded-lg px-4 py-2 font-semibold text-action-primary hover:bg-surface-subtle" href="#timecard-operations">Time &amp; Attendance</a>}
        {permissionCodes.includes("COMPANY_PAYROLL_REPORTING_READ") && <Link className="rounded-lg px-4 py-2 font-semibold text-action-primary hover:bg-surface-subtle" to="/payroll">Payroll</Link>}
      </nav>
      {selected ? <details open={Boolean(linkedEmployeeId && effectivePayPeriodId)} className="rounded-xl border border-stroke bg-surface-subtle p-4">
      <summary className="cursor-pointer font-semibold">Advanced workforce operations</summary>
      <div className="mt-4 space-y-6">
      <RealRosterActivationConsole />
      <Card className="p-4 sm:p-6">
        <h3 className="text-lg font-semibold">Source Employee certification</h3>
        <p className="mt-1 text-sm text-content-muted">Review exact source evidence and choose an explicit owner decision. ACP never matches by name or email.</p>
        {canCertifySources && <section className="mt-4" aria-label="Source Employee certification">
              <h4 className="font-semibold">Source Employee certification</h4>
              <p className="mt-1 text-xs text-content-muted">Review exact source evidence and choose an explicit owner decision. ACP never matches by name or email.</p>
              {sourceCertifications.query.isLoading ? <Spinner label="Loading source certification ledger" /> : sourceCertifications.query.isError ? <Alert className="mt-3" variant="danger">Source certification evidence is unavailable. No decision was inferred.</Alert> : <div className="mt-3 space-y-3">
                <p className="text-sm text-content-muted">{sourceCertifications.query.data?.total ?? 0} source identities · {sourceCertifications.query.data?.undecided ?? 0} decisions remaining</p>
                {sourceCertifications.query.data?.items.map((source) => {
                  const reason = sourceReasons[source.source_employee_id] ?? "";
                  const selectedEmployee = sourceEmployeeSelections[source.source_employee_id] ?? "";
                  const decide = (decision: "CONFIRM" | "SELECT_EXISTING" | "CREATE_ONBOARD" | "HOLD" | "LEGACY_ONLY", employeeId?: string) => sourceCertifications.decide.mutate({ sourceEmployeeId: source.source_employee_id, decision, expected_revision: source.revision, employee_id: employeeId, reason });
                  return <article className="rounded-md bg-surface-subtle p-3 text-xs" key={source.source_employee_id}>
                    <div className="flex flex-wrap justify-between gap-2"><span className="font-semibold">{source.source_system} · {source.source_employee_id}</span><Badge variant={source.decision === "CONFIRM" || source.decision === "SELECT_EXISTING" ? "success" : "neutral"}>{source.decision?.replaceAll("_", " ") ?? "Decision required"}</Badge></div>
                    <p className="mt-1 text-content-muted">Branch: {source.source_branch_name} · Evidence: {source.evidence_digest.slice(0, 12)}… · Revision {source.revision}</p>
                    <p className="mt-1">Mechanically supported ACP target: <strong>{source.mechanically_supported_employee_name ?? "None"}</strong></p>
                    {source.employee_name && <p className="mt-1">Current certified Employee: <strong>{source.employee_name}</strong></p>}
                    <label className="mt-3 block"><span className="font-medium">Owner reason</span><Input className="mt-1" value={reason} onChange={(event) => setSourceReasons((current) => ({ ...current, [source.source_employee_id]: event.target.value }))} placeholder="Record the human authority for this decision" /></label>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {source.mechanically_supported_employee_id && <Button variant="outline" disabled={reason.trim().length < 3 || sourceCertifications.decide.isPending} onClick={() => decide("CONFIRM")}>Confirm candidate</Button>}
                      <select aria-label={`Select existing Employee for ${source.source_employee_id}`} className="min-h-10 min-w-64 rounded-md border border-stroke bg-surface px-2" value={selectedEmployee} onChange={(event) => setSourceEmployeeSelections((current) => ({ ...current, [source.source_employee_id]: event.target.value }))}><option value="">Select another existing Employee</option>{(directory.data ?? []).map((employee) => <option key={employee.employee_id} value={employee.employee_id}>{employee.display_name} · {employee.employee_number}</option>)}</select>
                      <Button variant="outline" disabled={!selectedEmployee || reason.trim().length < 3 || sourceCertifications.decide.isPending} onClick={() => decide("SELECT_EXISTING", selectedEmployee)}>Select existing</Button>
                      <Button variant="outline" disabled={reason.trim().length < 3 || sourceCertifications.decide.isPending} onClick={() => decide("CREATE_ONBOARD")}>Create / onboard</Button>
                      <Button variant="outline" disabled={reason.trim().length < 3 || sourceCertifications.decide.isPending} onClick={() => decide("HOLD")}>Hold</Button>
                      <Button variant="outline" disabled={reason.trim().length < 3 || sourceCertifications.decide.isPending} onClick={() => decide("LEGACY_ONLY")}>Legacy only</Button>
                    </div>
                    {source.decision === "CREATE_ONBOARD" && permissionCodes.includes("COMPANY_IDENTITY_ONBOARDING_MANAGE") && <Link className="mt-2 inline-block font-semibold text-action-primary" to="/administration/identity-onboarding">Continue protected onboarding</Link>}
                    {source.history.length > 0 && <details className="mt-2"><summary className="cursor-pointer font-medium">Decision history ({source.history.length})</summary><ol className="mt-1 space-y-1 text-content-muted">{source.history.map((entry) => <li key={entry.revision}>Revision {entry.revision}: {entry.decision.replaceAll("_", " ")} · {entry.reason}</li>)}</ol></details>}
                  </article>;
                })}
              </div>}
            </section>}
        {!canCertifySources && <Alert variant="information">Workforce certification authority is required to review source identities.</Alert>}
      </Card>
      <Card className="p-4 sm:p-6">
        <h3 className="text-lg font-semibold">Assignment eligibility</h3>
        <p className="mt-1 text-sm text-content-muted">Evaluate explicit Branch, availability, capability, language, restriction, and assignment evidence. This does not assign work.</p>
        <form
          className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5"
          onSubmit={(event) => {
            event.preventDefault();
            eligibility.mutate({
              branch_id: branchId,
              window_start_at: new Date(windowStart).toISOString(),
              window_end_at: new Date(windowEnd).toISOString(),
              required_capability_codes: capabilities
                .split(",")
                .map((value) => value.trim())
                .filter(Boolean),
              required_language_codes: languages
                .split(",")
                .map((value) => value.trim())
                .filter(Boolean),
            });
          }}
        >
          <label className="text-sm">
            <span className="mb-1 block font-medium">Branch</span>
            <Select required value={branchId} onChange={(event) => setBranchId(event.target.value)}><option value="">Select an authorized Branch</option>{(activeCompany?.branches ?? []).map((branch) => <option value={branch.id} key={branch.id}>{branch.name}{branch.code ? ` (${branch.code})` : ""}</option>)}</Select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium">Window start</span>
            <Input required type="datetime-local" value={windowStart} onChange={(event) => setWindowStart(event.target.value)} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium">Window end</span>
            <Input required type="datetime-local" value={windowEnd} onChange={(event) => setWindowEnd(event.target.value)} />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium">Capabilities</span>
            <Input value={capabilities} onChange={(event) => setCapabilities(event.target.value)} placeholder="plumbing, technician" />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium">Languages</span>
            <Input value={languages} onChange={(event) => setLanguages(event.target.value)} placeholder="en, es" />
          </label>
          <button type="submit" disabled={eligibility.isPending} className="min-h-10 rounded-lg bg-action-primary px-4 font-semibold text-white disabled:opacity-50 md:col-span-2 xl:col-span-1">
            {eligibility.isPending ? "Evaluating…" : "Evaluate"}
          </button>
        </form>
        {eligibility.isError && (
          <div className="mt-4">
            <Alert variant="danger" title="Eligibility unavailable">
              The evidence could not be evaluated. Verify the authorized Branch and time window.
            </Alert>
          </div>
        )}
        {eligibility.data && (
          <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
            {eligibility.data.map((item) => (
              <div key={item.employee_id} className="rounded-xl border border-stroke p-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <strong>{item.display_name}</strong>
                    <p className="text-xs text-content-muted">{item.employee_number}</p>
                  </div>
                  <Badge variant={item.eligible ? "success" : "neutral"}>{item.decision}</Badge>
                </div>
                <p className="mt-2 text-xs text-content-muted">
                  {item.reasons.length ? item.reasons.join(" · ") : "No blockers"} · {item.availability_confidence}
                </p>
              </div>
            ))}
          </div>
        )}
      </Card>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="Owner morning Employee review">
        {[
          ["Authorized Employees", morningReview.total],
          ["Inactive identities", morningReview.inactive],
          ["Missing Workforce profile", morningReview.missingProfile],
          ["Readiness needs attention", morningReview.needsAttention],
        ].map(([label, value]) => (
          <Card key={String(label)} className="p-4">
            <p className="text-sm text-content-muted">{label}</p>
            <p className="mt-1 text-2xl font-bold">{value}</p>
          </Card>
        ))}
      </section>
      {canReviewTime && (
        <Card className="p-4 sm:p-6">
          <div id="timecard-operations" className="flex flex-wrap items-start justify-between gap-3 scroll-mt-4">
            <div>
              <h3 className="text-lg font-semibold">Current timecard review</h3>
              <p className="mt-1 text-sm text-content-muted">Read-only current-period evidence. Exceptions require human review; no Payroll execution occurs here.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {(payPeriods.data ?? []).length > 0 && (
                <label className="text-sm font-medium">
                  Pay period
                  <select aria-label="Timecard pay period" className="ml-2 min-h-10 rounded-lg border border-stroke bg-surface px-2" value={effectivePayPeriodId ?? ""} onChange={(event) => selectPayPeriod(event.target.value)}>
                    {(payPeriods.data ?? []).map((period) => (
                      <option key={period.id} value={period.id}>
                        {period.period_start} – {period.period_end}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {permissionCodes.includes("COMPANY_PAYROLL_REPORTING_READ") && (
                <Link className="rounded-lg border border-stroke px-3 py-2 text-sm font-semibold" to={`/payroll${effectivePayPeriodId ? `?period=${effectivePayPeriodId}` : ""}`}>
                  Review Payroll period
                </Link>
              )}
            </div>
          </div>
          {timeReview.isLoading && (
            <div className="mt-4">
              <Spinner label="Loading timecard review" />
            </div>
          )}
          {timeReview.isError && (
            <div className="mt-4">
              <Alert variant="warning" title="Timecard review unavailable">
                No time or Payroll state was changed. Refresh after verifying timekeeping authority.
              </Alert>
            </div>
          )}
          {timeReview.data && !timeReview.data.pay_period && !effectivePayPeriodId && (
            <div className="mt-4">
              <Alert variant="warning" title="Pay period required">
                Configure an authorized pay period before preparing payroll time evidence.
              </Alert>
            </div>
          )}
          {timeReview.data?.pay_period && (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead>
                  <tr className="border-b border-stroke text-content-muted">
                    <th className="py-2">Employee</th>
                    <th>Entries</th>
                    <th>Recorded hours</th>
                    <th>Review state</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {timeReview.data.items.map((item) => (
                    <tr className="border-b border-stroke" key={item.employee_id}>
                      <td className="py-3">
                        <strong>{item.display_name}</strong>
                        <span className="block text-xs text-content-muted">{item.employee_number}</span>
                      </td>
                      <td>{item.entry_count}</td>
                      <td>{(item.total_minutes / 60).toFixed(2)}</td>
                      <td>
                        <div className="flex flex-wrap gap-1">
                          {item.exception_codes.length ? (
                            item.exception_codes.map((code) => (
                              <Badge variant={code === "overlap" ? "danger" : "warning"} key={code}>
                                {code.replaceAll("_", " ")}
                              </Badge>
                            ))
                          ) : (
                            <Badge variant="success">ready for review</Badge>
                          )}
                        </div>
                      </td>
                      <td>
                        <div className="flex flex-wrap gap-2">
                          {canApproveTime && item.entries.filter((entry) => entry.state === "submitted").map((entry) => (
                            <button
                              type="button"
                              className="rounded-lg bg-action-primary px-3 py-2 font-medium text-white disabled:opacity-50"
                              disabled={timeApproval.isPending}
                              key={entry.revision_id}
                              onClick={() => setPendingTimeApproval({
                                revisionId: entry.revision_id,
                                employeeName: item.display_name,
                                workDate: entry.work_date,
                              })}
                            >
                              Approve {entry.work_date}
                            </button>
                          ))}
                          {canCorrectTime && item.entries.length > 0 && (
                            <button
                              type="button"
                              className="rounded-lg border border-stroke px-3 py-2 font-medium"
                              onClick={() => {
                                const entry = item.entries[item.entries.length - 1];
                                setCorrectionRevision(entry.revision_id);
                                setCorrectionStart(entry.start_at?.slice(0, 16) ?? "");
                                setCorrectionEnd(entry.end_at?.slice(0, 16) ?? "");
                              }}
                            >
                              Review correction
                            </button>
                          )}
                          {!canApproveTime && !canCorrectTime && <span className="text-content-muted">Read only</span>}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {pendingTimeApproval && (
            <ConfirmationDialog
              title="Approve submitted time?"
              description="Approval creates accepted time evidence for downstream Payroll review."
              confirmLabel="Approve time"
              pending={timeApproval.isPending}
              onCancel={() => setPendingTimeApproval(null)}
              onConfirm={() => timeApproval.mutate(pendingTimeApproval.revisionId, {
                onSuccess: () => setPendingTimeApproval(null),
              })}
            >
              <p><strong>{pendingTimeApproval.employeeName}</strong></p>
              <p>Work date: {pendingTimeApproval.workDate}</p>
            </ConfirmationDialog>
          )}
          {timeApproval.isError && (
            <div className="mt-4">
              <Alert variant="danger" title="Time was not approved">
                Refresh the current review and verify the submitted revision and approval authority.
              </Alert>
            </div>
          )}
          {correctionRevision && (
            <form
              className="mt-5 grid gap-3 rounded-xl border border-stroke p-4 md:grid-cols-2"
              onSubmit={(event) => {
                event.preventDefault();
                timeCorrection.mutate(
                  {
                    revisionId: correctionRevision,
                    input: {
                      correction_kind: correctionKind,
                      start_at: correctionStart ? new Date(correctionStart).toISOString() : null,
                      end_at: correctionEnd ? new Date(correctionEnd).toISOString() : null,
                      approved_duration_minutes: null,
                      reason: correctionReason,
                    },
                  },
                  {
                    onSuccess: () => {
                      setCorrectionRevision("");
                      setCorrectionReason("");
                    },
                  },
                );
              }}
            >
              <label className="text-sm">
                <span className="mb-1 block font-medium">Correction case</span>
                <select className="min-h-10 w-full rounded-lg border border-stroke bg-surface px-2" value={correctionKind} onChange={(event) => setCorrectionKind(event.target.value as typeof correctionKind)}>
                  <option value="missing_clock_out">Missing clock-out</option>
                  <option value="incorrect_job">Incorrect Job attribution</option>
                  <option value="missing_interval">Missing interval</option>
                  <option value="overlapping_intervals">Overlapping intervals</option>
                  <option value="incorrect_start">Incorrect start</option>
                  <option value="incorrect_stop">Incorrect stop</option>
                </select>
              </label>
              <label className="text-sm">
                <span className="mb-1 block font-medium">Reviewer explanation</span>
                <Input required value={correctionReason} onChange={(event) => setCorrectionReason(event.target.value)} placeholder="Explain the evidence supporting this correction" />
              </label>
              <label className="text-sm">
                <span className="mb-1 block font-medium">Corrected start</span>
                <Input required type="datetime-local" value={correctionStart} onChange={(event) => setCorrectionStart(event.target.value)} />
              </label>
              <label className="text-sm">
                <span className="mb-1 block font-medium">Corrected stop</span>
                <Input required type="datetime-local" value={correctionEnd} onChange={(event) => setCorrectionEnd(event.target.value)} />
              </label>
              <div className="flex gap-2 md:col-span-2">
                <button type="submit" disabled={timeCorrection.isPending} className="rounded-lg bg-action-primary px-4 py-2 font-semibold text-white disabled:opacity-50">
                  {timeCorrection.isPending ? "Saving…" : "Create audited revision"}
                </button>
                <button type="button" className="rounded-lg border border-stroke px-4 py-2" onClick={() => setCorrectionRevision("")}>
                  Cancel
                </button>
              </div>
              {timeCorrection.isError && (
                <div className="md:col-span-2">
                  <Alert variant="danger" title="Correction not applied">
                    Refresh the current revision and verify the interval, Branch authority, and overlap evidence.
                  </Alert>
                </div>
              )}
            </form>
          )}
          <h3 className="mt-6 text-lg font-semibold">Detailed timecards</h3>
          {timecards.isLoading && (
            <div className="mt-4">
              <Spinner label="Loading detailed Employee timecards" />
            </div>
          )}
          {timecards.isError && (
            <div className="mt-4">
              <Alert variant="warning" title="Timecard detail unavailable">
                The current summary remains available. No time evidence was changed.
              </Alert>
            </div>
          )}
          {timecards.data && (
            <div className="mt-5 space-y-3">
              <Alert variant="information" title="Job attribution is partial">
                Paid-time evidence is shown exactly as recorded. Hours without explicit Job evidence remain unclassified rather than being assigned to a Job.
              </Alert>
              {timecards.data.employees.map((employee) => (
                <details id={`timecard-${employee.employee_id}`} className="scroll-mt-4 rounded-xl border border-stroke p-3" key={employee.employee_id} open={linkedEmployeeId === employee.employee_id}>
                  <summary className="cursor-pointer list-none">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <strong>{employee.display_name}</strong>
                        <span className="ml-2 text-xs text-content-muted">{employee.employee_number}</span>
                        <p className="text-xs text-content-muted">
                          {(employee.accepted_minutes / 60).toFixed(2)} accepted / {(employee.total_supported_minutes / 60).toFixed(2)} supported hours
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {employee.active_open_clock && <Badge variant="warning">open clock</Badge>}
                        {employee.missing_clock_out && <Badge variant="danger">missing clock-out</Badge>}
                        <Badge variant={employee.review_state === "ACCEPTED" ? "success" : "warning"}>{employee.review_state.replaceAll("_", " ")}</Badge>
                      </div>
                    </div>
                  </summary>
                  <div className="mt-4 space-y-4">
                    {employee.days.length > 0 && (
                      <section aria-label={`${employee.display_name} weekly timecard totals`}>
                        <h4 className="mb-2 font-semibold">Weekly totals</h4>
                        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                          {weeklyTimecardSummaries(employee, timecards.data.pay_period.period_start).map(([week, summary]) => (
                            <div className="rounded-lg bg-surface-subtle p-3 text-sm" key={week}>
                              <div className="flex items-center justify-between gap-2">
                                <strong>Week {week + 1}</strong>
                                <Badge variant={summary.needsReview ? "warning" : "success"}>{summary.needsReview ? "needs review" : "accepted"}</Badge>
                              </div>
                              <p className="mt-1 text-content-muted">
                                {(summary.supported / 60).toFixed(2)} supported · {(summary.accepted / 60).toFixed(2)} accepted hours
                              </p>
                            </div>
                          ))}
                        </div>
                      </section>
                    )}
                    {employee.days.length ? (
                      employee.days.map((day) => (
                        <section key={day.work_date}>
                          <div className="mb-2 flex flex-wrap justify-between gap-2">
                            <h4 className="font-semibold">{day.work_date}</h4>
                            <span className="text-sm text-content-muted">
                              {(day.total_supported_minutes / 60).toFixed(2)} hours · {day.unclassified_minutes ? `${(day.unclassified_minutes / 60).toFixed(2)} unclassified` : "classified"}
                            </span>
                          </div>
                          <div className="overflow-x-auto">
                            <table className="w-full min-w-[760px] text-left text-sm">
                              <thead>
                                <tr className="text-content-muted">
                                  <th>Worked interval</th>
                                  <th>Job</th>
                                  <th>Hours</th>
                                  <th>Evidence</th>
                                  <th>Review</th>
                                  <th>Audit</th>
                                </tr>
                              </thead>
                              <tbody>
                                {day.intervals.map((entry) => (
                                  <tr className="border-t border-stroke" key={entry.revision_id}>
                                    <td className="py-2">{entry.start_at && entry.end_at ? `${new Date(entry.start_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} – ${new Date(entry.end_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}` : "Supported duration"}</td>
                                    <td>{entry.job_number ?? "Not attributed"}</td>
                                    <td>{(entry.supported_minutes / 60).toFixed(2)}</td>
                                    <td>
                                      <div className="flex gap-1">
                                        {entry.corrected && <Badge variant="warning">corrected</Badge>}
                                        {entry.overlap && <Badge variant="danger">overlap</Badge>}
                                        <Badge variant="neutral">{entry.provenance.replaceAll("_", " ")}</Badge>
                                      </div>
                                    </td>
                                    <td>{entry.review_state.replaceAll("_", " ")}</td>
                                    <td title={entry.audit_digest}>Revision {entry.revision_number} · verified</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </section>
                      ))
                    ) : (
                      <p className="text-sm text-content-muted">No supported time entries in this pay period.</p>
                    )}
                  </div>
                </details>
              ))}
            </div>
          )}
        </Card>
      )}
      </div>
      </details> : null}
      <div id="employee-roster" className={`scroll-mt-4 gap-6 ${selected ? "grid xl:grid-cols-[minmax(20rem,0.85fr)_minmax(0,1.4fr)]" : "block"}`}>
        <Card className="min-w-0 overflow-hidden">
          <div className="space-y-3 border-b border-stroke p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold">Workforce</h3>
                <p className="mt-1 text-sm text-content-muted">Current employees and access readiness. Select a person for their full profile and history.</p>
              </div>
              <div className="flex rounded-lg border border-stroke bg-surface-subtle p-1" aria-label="Workforce view">
                <button type="button" className={`rounded-md px-3 py-2 text-sm font-semibold ${viewMode === "list" ? "bg-action-primary text-white" : "text-content-muted hover:text-content"}`} onClick={() => setViewMode("list")}>List</button>
                <button type="button" className={`rounded-md px-3 py-2 text-sm font-semibold ${viewMode === "org-chart" ? "bg-action-primary text-white" : "text-content-muted hover:text-content"}`} onClick={() => setViewMode("org-chart")}>Org chart</button>
              </div>
            </div>
            <label className="relative block">
              <span className="sr-only">Search workforce</span>
              <Search size={17} className="absolute left-3 top-3 text-content-muted" />
              <Input className="pl-10" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, number, role, capability, language" />
            </label>
            <div className="grid gap-2 sm:grid-cols-3">
              <label className="text-xs text-content-muted">
                Branch
                <select aria-label="Branch" className="mt-1 min-h-10 w-full rounded-lg border border-stroke bg-surface px-2 text-content" value={branchFilter} onChange={(event) => setBranchFilter(event.target.value)}>
                  <option value="">All authorized</option>
                  {(activeCompany?.branches ?? []).map((branch) => (
                    <option key={branch.id} value={branch.id}>
                      {branch.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-xs text-content-muted">
                Employee status
                <select aria-label="Filter by Employee status" className="mt-1 min-h-10 w-full rounded-lg border border-stroke bg-surface px-2 text-content" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                  <option value="active">Active</option>
                  <option value="former">Former Employees</option>
                  <option value="">All</option>
                </select>
              </label>
              <label className="text-xs text-content-muted">
                Readiness
                <select aria-label="Filter by readiness" className="mt-1 min-h-10 w-full rounded-lg border border-stroke bg-surface px-2 text-content" value={readinessFilter} onChange={(event) => setReadinessFilter(event.target.value)}>
                  <option value="">All</option>
                  <option value="READY">Ready</option>
                  <option value="BLOCKED">Blocked</option>
                  <option value="INSUFFICIENT_EVIDENCE">Insufficient evidence</option>
                </select>
              </label>
            </div>
          </div>
          {directory.isLoading && (
            <div className="p-8">
              <Spinner label="Loading workforce" />
            </div>
          )}
          {directory.isError &&
            (() => {
              const error = getOperatorApiError(directory.error, "workforce directory");
              return (
                <div className="p-4">
                  <Alert variant="danger" title={error.title}>
                    {error.message}
                  </Alert>
                </div>
              );
            })()}
          {viewMode === "list" ? (
            <div className="divide-y divide-stroke">
              {filtered.map((employee) => (
                <button key={employee.employee_id} type="button" onClick={() => openEmployee(employee.employee_id)} className="block min-h-16 w-full p-4 text-left hover:bg-surface-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus">
                  <span className="flex flex-wrap items-start justify-between gap-3">
                    <span className="min-w-0">
                      <span className="block truncate font-semibold">{employee.display_name}</span>
                      <span className="mt-1 block truncate text-sm text-content-muted">{visiblePosition(employee)} · {branchName(employee.home_branch_id)}</span>
                    </span>
                    <span className="flex flex-wrap gap-1">
                      <Badge variant={employee.employee_status === "active" ? "success" : "neutral"}>{employee.employee_status === "active" ? "ACTIVE" : employee.employee_status.toUpperCase()}</Badge>
                      <OwnerAttention state={employee.readiness_state} />
                    </span>
                  </span>
                  <span className="mt-3 grid gap-2 text-xs text-content-muted sm:grid-cols-3">
                    <span><strong className="font-semibold text-content">Login readiness</strong><br />{employee.profile_status === "active" ? "LOGIN READY" : "LOGIN NEEDS SETUP"}</span>
                    <span><strong className="font-semibold text-content">Mobile readiness</strong><br />{employee.technician ? "MOBILE READY" : "REVIEW NEEDED"}</span>
                    <span><strong className="font-semibold text-content">Payroll readiness</strong><br />PAYROLL REVIEW</span>
                  </span>
                </button>
              ))}
              {filteredHistorical.map((identity) => (
                <button key={`historical:${identity.id}`} type="button" onClick={() => openEmployee(`historical:${identity.id}`)} className="block min-h-16 w-full border-t border-stroke bg-surface-subtle/40 p-4 text-left hover:bg-surface-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus">
                  <span className="flex flex-wrap items-start justify-between gap-3"><span className="min-w-0"><span className="block truncate font-semibold">{identity.display_name}</span><span className="mt-1 block truncate text-sm text-content-muted">{identity.source_system} · {identity.source_status ?? identity.lifecycle_state} · source-only history</span></span><Badge variant="neutral">HISTORICAL</Badge></span>
                  <span className="mt-3 block text-xs text-content-muted">{identity.provenance_reference}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="space-y-4 p-4">
              {["Company administrators / owners", "Office / management", "Field managers", "Technicians", "Helpers", "Other explicit roles"].map((group) => {
                const members = filtered.filter((employee) => workforceGroup(employee) === group);
                if (!members.length) return null;
                return <section key={group} aria-labelledby={`workforce-group-${group.replaceAll(" ", "-")}`}>
                  <h4 id={`workforce-group-${group.replaceAll(" ", "-")}`} className="mb-2 text-sm font-semibold text-content-muted">{group}</h4>
                  <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                    {members.map((employee) => <button key={employee.employee_id} type="button" onClick={() => openEmployee(employee.employee_id)} className="rounded-xl border border-stroke bg-surface-subtle p-3 text-left hover:border-action-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus">
                      <div className="flex items-start justify-between gap-2"><strong>{employee.display_name}</strong><Badge variant={employee.employee_status === "active" ? "success" : "neutral"}>{employee.employee_status.toUpperCase()}</Badge></div>
                      <p className="mt-1 text-sm text-content-muted">{visiblePosition(employee)} · {branchName(employee.home_branch_id)}</p>
                    </button>)}
                  </div>
                </section>;
              })}
              {filteredHistorical.length > 0 && <section aria-labelledby="historical-workforce-group"><h4 id="historical-workforce-group" className="mb-2 text-sm font-semibold text-content-muted">Historical / former source identities</h4><div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">{filteredHistorical.map((identity) => <button key={`historical:${identity.id}`} type="button" onClick={() => openEmployee(`historical:${identity.id}`)} className="rounded-xl border border-stroke bg-surface-subtle p-3 text-left hover:border-action-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus"><div className="flex items-start justify-between gap-2"><strong>{identity.display_name}</strong><Badge variant="neutral">HISTORICAL</Badge></div><p className="mt-1 text-sm text-content-muted">{identity.source_system} · {identity.source_status ?? identity.lifecycle_state}</p></button>)}</div></section>}
            </div>
          )}
          {directory.isSuccess && filtered.length === 0 && filteredHistorical.length === 0 && <p className="p-5 text-sm text-content-muted">No authorized Employee or retained historical identity matches this search.</p>}
        </Card>
        {!selected ? (
          <Card className="flex min-h-72 items-center justify-center p-8 text-center">
            <div>
              <UsersRound className="mx-auto text-action-primary" />
              <h3 className="mt-3 text-xl font-semibold">Choose an employee</h3>
              <p className="mt-2 text-sm text-content-muted">Open a profile for contact, access, dispatch, payroll, and historical detail.</p>
            </div>
          </Card>
        ) : selectedHistorical ? (
          <Card className="min-w-0 p-4 sm:p-6"><div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-sm text-action-primary">{selectedHistorical.source_system} · {selectedHistorical.source_identity}</p><h3 className="mt-1 text-2xl font-bold">{selectedHistorical.display_name}</h3><p className="mt-1 text-content-muted">Retained historical source identity</p></div><div className="flex items-center gap-2"><Badge variant="neutral">{selectedHistorical.lifecycle_state}</Badge><button type="button" className="rounded-lg border border-stroke px-3 py-2 text-sm font-semibold hover:bg-surface-subtle" onClick={closeEmployee}>Back to Workforce</button></div></div><dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2"><div><dt className="text-content-muted">Source status</dt><dd className="font-medium">{selectedHistorical.source_status ?? "Unavailable"}</dd></div><div><dt className="text-content-muted">Operational access</dt><dd className="font-medium">{selectedHistorical.operational_access_enabled ? "Enabled" : "Not enabled"}</dd></div><div><dt className="text-content-muted">Provenance</dt><dd className="break-words font-medium">{selectedHistorical.provenance_reference}</dd></div><div><dt className="text-content-muted">Evidence</dt><dd className="break-words font-medium">{selectedHistorical.evidence_digest ?? "Evidence digest unavailable"}</dd></div></dl>{selectedHistorical.unresolved_reason && <Alert className="mt-5" variant="warning" title="Historical identity remains source-only">{selectedHistorical.unresolved_reason} No Employee was reactivated or created from this record.</Alert>}</Card>
        ) : detail.isLoading ? (
          <Card className="p-8">
            <Spinner label="Loading Employee profile" />
          </Card>
        ) : detail.isError || !detail.data ? (
          <Alert variant="danger" title="Employee profile unavailable">
            The profile could not be loaded within the current Company and Branch authority.
          </Alert>
        ) : (
          <Card className="min-w-0 p-4 sm:p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-sm text-action-primary">{detail.data.employee_number}</p>
                <h3 className="mt-1 text-2xl font-bold">{detail.data.display_name}</h3>
                <p className="mt-1 text-content-muted">{visiblePosition(detail.data)}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2"><Readiness state={detail.data.readiness_state} /><button type="button" className="rounded-lg border border-stroke px-3 py-2 text-sm font-semibold hover:bg-surface-subtle" onClick={closeEmployee}>Back to Workforce</button></div>
            </div>
            <nav aria-label="Employee detail" className="mt-5 flex gap-1 overflow-x-auto border-b border-stroke pb-1" role="tablist">
              {((canAdministerIdentity ? ["overview", "access", "time", "payroll", "history"] : ["overview", "time", "payroll", "history"]) as Array<typeof detailTab>).map((tab) => <button key={tab} type="button" role="tab" aria-selected={detailTab === tab} className={`whitespace-nowrap rounded-t-lg px-3 py-2 text-sm font-semibold ${detailTab === tab ? "border-b-2 border-action-primary text-action-primary" : "text-content-muted hover:bg-surface-subtle hover:text-content"}`} onClick={() => setDetailTab(tab)}>{tab === "overview" ? "Overview" : tab[0].toUpperCase() + tab.slice(1)}</button>)}
            </nav>
            {detailTab === "overview" && <section id="employee-personal" className="mt-5 space-y-5" aria-label="Employee overview">
              <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                <div><dt className="text-content-muted">Position</dt><dd className="font-medium">{visiblePosition(detail.data)}</dd></div>
                <div><dt className="text-content-muted">Status</dt><dd className="font-medium">{detail.data.employee_status === "active" ? "ACTIVE" : detail.data.employee_status.toUpperCase()}</dd></div>
                <div><dt className="text-content-muted">Branch</dt><dd className="font-medium">{branchName(detail.data.home_branch_id)}</dd></div>
                <div><dt className="text-content-muted">Phone</dt><dd className="font-medium">{detail.data.phone ?? "Not provided"}</dd></div>
                <div><dt className="text-content-muted">Email</dt><dd className="break-all font-medium">{administration.data?.login_email ?? "Not configured"}</dd></div>
                <div><dt className="text-content-muted">Employment dates</dt><dd className="font-medium">{detail.data.hire_date ?? "Hire date unavailable"} – {detail.data.termination_date ?? "Present"}</dd></div>
                <div><dt className="text-content-muted">Availability</dt><dd className="font-medium">{detail.data.availability.length ? `${detail.data.availability.length} recorded window${detail.data.availability.length === 1 ? "" : "s"}` : "Uses Branch schedule"}</dd></div>
              </dl>
              {detail.data.availability.length > 0 && <div className="rounded-xl bg-surface-subtle p-3 text-sm">
                <p className="font-semibold">Scheduling availability</p>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  {detail.data.availability.slice(0, 4).map((item) => <p key={`${item.branch_id}-${item.start_at}-${item.end_at}`}><span className="font-medium">{item.status}</span> · {new Date(item.start_at).toLocaleString()} – {new Date(item.end_at).toLocaleString()}</p>)}
                </div>
              </div>}
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-xl bg-surface-subtle p-3"><p className="text-xs text-content-muted">Login</p><p className="mt-1 font-semibold">{administration.data?.access_status === "ACTIVE" ? "LOGIN READY" : "LOGIN NEEDS SETUP"}</p></div>
                <div className="rounded-xl bg-surface-subtle p-3"><p className="text-xs text-content-muted">Mobile</p><p className="mt-1 font-semibold">{administration.data?.mobile_readiness === "READY" ? "MOBILE READY" : "REVIEW NEEDED"}</p></div>
                <div className="rounded-xl bg-surface-subtle p-3"><p className="text-xs text-content-muted">Payroll</p><p className="mt-1 font-semibold">PAYROLL REVIEW</p></div>
              </div>
              <div className="flex flex-wrap gap-2" aria-label="Employee quick actions">
                <Button type="button" variant="secondary" disabled={!canAdministerEmployees} onClick={() => { setEditPhone(detail.data.phone ?? ""); setEditJobTitle(detail.data.job_title ?? ""); setEditBranchId(detail.data.home_branch_id ?? ""); setEditingEmployee(detail.data.employee_id); }}>Edit Employee</Button>
                <Button type="button" variant="outline" onClick={() => setDetailTab("history")}>View History</Button>
                {canAdministerEmployees && detail.data.employee_status === "active" && <Button type="button" variant="destructive" onClick={() => { setDeactivationReason(""); setConfirmDeactivation(true); }}>Deactivate Employee</Button>}
              </div>
              {editingEmployee === detail.data.employee_id && <form className="rounded-xl border border-stroke bg-surface-subtle p-4" onSubmit={(event) => {
                event.preventDefault();
                profileUpdate.mutate({
                  phone: editPhone.trim() || null,
                  job_title: editJobTitle.trim() || null,
                  home_branch_id: editBranchId || null,
                  expected_updated_at: detail.data.updated_at,
                }, { onSuccess: () => setEditingEmployee(null) });
              }}>
                <h4 className="font-semibold">Edit Employee</h4>
                <p className="mt-1 text-sm text-content-muted">Update ordinary employee details. Access roles and security controls remain in Administration.</p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <label className="text-sm">Phone<Input className="mt-1" value={editPhone} onChange={(event) => setEditPhone(event.target.value)} /></label>
                  <label className="text-sm">Position<Input className="mt-1" value={editJobTitle} onChange={(event) => setEditJobTitle(event.target.value)} /></label>
                  <label className="text-sm">Branch<select className="mt-1 min-h-10 w-full rounded-lg border border-stroke bg-surface px-2" value={editBranchId} onChange={(event) => setEditBranchId(event.target.value)}><option value="">Company-wide / unassigned</option>{(activeCompany?.branches ?? []).map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</select></label>
                </div>
                {profileUpdate.isError && <Alert className="mt-3" variant="danger">Employee details were not saved. Refresh and try again if another administrator changed this profile.</Alert>}
                <div className="mt-4 flex flex-wrap gap-2"><Button type="submit" disabled={profileUpdate.isPending}>{profileUpdate.isPending ? "Saving…" : "Save Employee"}</Button><Button type="button" variant="outline" onClick={() => setEditingEmployee(null)}>Cancel</Button></div>
              </form>}
            </section>}
            {detailTab === "access" && canAdministerIdentity && <section className="mt-5 space-y-5" aria-label="Employee access editor">
              <div>
                <div className="flex flex-wrap items-center justify-between gap-2"><h4 className="text-lg font-semibold">Access profile</h4>{permissionDraftDirty && <Badge variant="warning">UNSAVED CHANGES</Badge>}{selectedProfile === "CUSTOM" && <Badge variant="warning">CUSTOMIZED</Badge>}</div>
                <p className="mt-1 text-sm text-content-muted">Choose a standard profile, then adjust individual permissions. Nothing is saved until you choose Save changes.</p>
                <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {ACCESS_PROFILES.map((profile) => <button key={profile.code} type="button" aria-pressed={activeProfile === profile.code} disabled={!canManageMembership || permissionPresetPending || permissionUpdate.isPending} onClick={() => void applyAccessProfile(profile.code)} className={`rounded-xl border p-3 text-left transition ${activeProfile === profile.code ? "border-action-primary bg-action-primary/10" : "border-stroke bg-surface-subtle hover:border-action-primary"}`}><span className="block font-semibold">{profile.label}</span><span className="mt-1 block text-xs text-content-muted">{activeProfile === profile.code ? "Selected" : "Use standard profile"}</span></button>)}
                  <button type="button" aria-pressed={activeProfile === "CUSTOM"} disabled={!canManageMembership || permissionUpdate.isPending} onClick={() => setSelectedProfile("CUSTOM")} className={`rounded-xl border p-3 text-left ${activeProfile === "CUSTOM" ? "border-action-primary bg-action-primary/10" : "border-stroke bg-surface-subtle hover:border-action-primary"}`}><span className="block font-semibold">Custom</span><span className="mt-1 block text-xs text-content-muted">Adjust after selecting a profile</span></button>
                </div>
              </div>
              <div><h4 className="text-lg font-semibold">Permissions</h4><div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {PERMISSION_GROUPS.map((group) => <section className="rounded-xl border border-stroke bg-surface-subtle p-3" key={group.label}><h5 className="font-semibold">{group.label}</h5><div className="mt-2 space-y-2">{group.options.map((option) => { const available = administration.data?.permissions.some((permission) => permission.code === option.code); const checked = draftPermissionCodes.has(option.code); return <label className={`flex min-h-9 items-center gap-2 text-sm ${available ? "cursor-pointer" : "cursor-not-allowed text-content-muted"}`} key={option.code}><input type="checkbox" checked={checked} disabled={!canManageMembership || !available || permissionUpdate.isPending} onChange={() => { const next = new Set(draftPermissionCodes); if (next.has(option.code)) next.delete(option.code); else next.add(option.code); setSelectedProfile("CUSTOM"); setPermissionDraft(next); }} /><span>{option.label}</span>{!available && <span className="text-xs text-content-muted">Unavailable</span>}</label>; })}</div></section>)}
              </div></div>
              {(permissionMessage || permissionError) && <Alert className="mt-4" variant={permissionError ? "danger" : "success"}>{permissionError ?? permissionMessage}</Alert>}
              <div className="sticky bottom-3 z-10 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-stroke bg-surface p-3 shadow-lg" aria-label="Permission editor actions">
                <span className="text-sm text-content-muted">{permissionDraftDirty ? "You have unsaved permission changes." : "Saved permissions"}</span>
                <div className="flex gap-2"><Button variant="outline" disabled={!permissionDraftDirty || permissionUpdate.isPending} onClick={cancelPermissionDraft}>Cancel</Button><Button variant="primary" disabled={!permissionDraftDirty || permissionUpdate.isPending || permissionPresetPending} onClick={savePermissionDraft}>{permissionUpdate.isPending ? "Saving…" : "Save changes"}</Button></div>
              </div>
            </section>}
            {detailTab === "time" && <section className="mt-5 rounded-xl border border-stroke bg-surface-subtle p-4"><h4 className="text-lg font-semibold">Time</h4><p className="mt-1 text-sm text-content-muted">Review current time and attendance from the Time workspace.</p>{canReviewTime ? <a className="mt-3 inline-block font-semibold text-action-primary underline" href={`#timecard-${detail.data.employee_id}`}>Open time review</a> : <p className="mt-3 text-sm text-content-muted">Time review is not available for this account.</p>}</section>}
            {detailTab === "payroll" && <section className="mt-5 rounded-xl border border-stroke bg-surface-subtle p-4"><h4 className="text-lg font-semibold">Payroll</h4><p className="mt-1 text-sm text-content-muted">Payroll readiness is reviewed separately from access. No payroll action is performed from this summary.</p>{permissionCodes.includes("COMPANY_PAYROLL_REPORTING_READ") && <Link className="mt-3 inline-block font-semibold text-action-primary underline" to={`/payroll?employee=${detail.data.employee_id}#payroll-employee-${detail.data.employee_id}`}>Open payroll setup</Link>}</section>}
            {detailTab === "history" && <section id="employee-history" className="mt-5 rounded-xl border border-stroke p-4" aria-label="Employee history">
              <div className="flex flex-wrap items-start justify-between gap-3"><div><h4 className="font-semibold">Employee history</h4><p className="mt-1 text-sm text-content-muted">Complete audit and operational history for this employee.</p></div><Badge variant="neutral">{timeline.data?.items.length ?? 0} events</Badge></div>
              {timeline.isLoading && <div className="mt-3"><Spinner label="Loading Employee history" /></div>}
              {timeline.isError && <div className="mt-3"><Alert variant="warning">Employee history is unavailable. No historical event was inferred.</Alert></div>}
              {timeline.data && <ol className="mt-3 space-y-3">
                {timeline.data.items.map((item, index) => <li className="rounded-lg bg-surface-subtle p-3 text-sm" key={`${item.event_type}-${item.occurred_at}-${index}`}>
                  <div className="flex flex-wrap items-start justify-between gap-2"><strong>{item.event_type.replaceAll("_", " ")}</strong><Badge variant={item.authority === "ACP_NATIVE" ? "success" : "neutral"}>{item.authority.replaceAll("_", " ")}</Badge></div>
                  <p className="mt-1">{item.description}</p>
                  <p className="mt-1 text-xs text-content-muted">{new Date(item.occurred_at).toLocaleString()} · {item.source.replaceAll("_", " ")}{item.actor_display_name ? ` · ${item.actor_display_name}` : ""}</p>
                  {item.navigation_reference && <Link className="mt-2 inline-block font-semibold text-action-primary" to={item.navigation_reference}>Open related workspace</Link>}
                </li>)}
                {timeline.data.items.length === 0 && <li className="text-sm text-content-muted">No employee history is available.</li>}
              </ol>}
            </section>}
            {canAdministerIdentity && <details id="employee-advanced" className="mt-5 rounded-xl border border-stroke bg-surface-subtle p-4">
              <summary className="cursor-pointer font-semibold">Advanced / Evidence</summary>
              <div className="mt-4 space-y-5">
            {detail.data.readiness_blockers.length > 0 && (
              <section className="mt-5 rounded-xl border border-status-warning/40 bg-status-warning/5 p-4">
                <h4 className="font-semibold">Employment blockers</h4>
                <ReadinessBlockers blockers={detail.data.readiness_blockers} />
                <p className="mt-3 text-sm text-content-muted">Basic technician eligibility now derives from active employment, effective Field Operations access, Branch schedule, and explicit exceptions. Skills remain evidence; genuine credentials and restrictions remain hard constraints.</p>
              </section>
            )}
            {canAdministerEmployees && administration.isLoading && (
              <div className="mt-5">
                <Spinner label="Loading Employee administration" />
              </div>
            )}
            {canAdministerEmployees && administration.isError && (
              <div className="mt-5">
                <Alert variant="danger" title="Employee administration unavailable">
                  Operational Workforce evidence remains visible, but identity and permission readiness could not be loaded.
                </Alert>
              </div>
            )}
            {administration.data && (
              <section className="mt-5 rounded-xl border border-stroke p-4" aria-labelledby="employee-access-heading">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h4 id="employee-access-heading" className="font-semibold">
                      Identity, access, and Mobile readiness
                    </h4>
                    <p className="mt-1 text-sm text-content-muted">User, Membership, Branch grants, canonical roles, and effective permissions remain distinct authorities.</p>
                  </div>
                  <Badge variant={administration.data.mobile_readiness === "READY" ? "success" : "warning"}>{administration.data.mobile_readiness.replaceAll("_", " ")}</Badge>
                </div>
                <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
                  <div>
                    <dt className="text-content-muted">Email</dt>
                    <dd className="break-all font-medium">{administration.data.login_email ?? administration.data.masked_login ?? "Unavailable"}</dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Role</dt>
                    <dd className="font-medium">{administration.data.role_codes.length ? administration.data.role_codes.map((code) => code.replaceAll("_", " ")).join(", ") : "Not assigned"}</dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Branch</dt>
                    <dd className="font-medium">{branchName(administration.data.home_branch_id)}</dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Employee access</dt>
                    <dd className={`font-semibold ${administration.data.access_status === "LOCKED" ? "text-status-danger" : ""}`}>
                      ACCESS {administration.data.access_status === "ACTIVE" ? "ACTIVE" : administration.data.access_status}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Invite status</dt>
                    <dd className="font-medium">{administration.data.invitation_status?.replaceAll("_", " ") ?? "Not prepared"}</dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Email delivery</dt>
                    <dd className="font-medium">{administration.data.delivery_status === "accepted" ? "Provider accepted" : administration.data.delivery_status?.replaceAll("_", " ") ?? "Not prepared"}</dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Account</dt>
                    <dd className="font-medium">{administration.data.onboarding_status?.replaceAll("_", " ") ?? administration.data.user_status ?? "Not linked"}</dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Employment</dt>
                    <dd className="font-medium">{administration.data.employee_status === "active" ? "Active" : "Disabled"}</dd>
                  </div>
                </dl>
                {administration.data.access_status === "LOCKED" && (
                  <Alert className="mt-4" variant="danger" title="Access locked">
                    Locked {administration.data.access_locked_at ? new Date(administration.data.access_locked_at).toLocaleString() : "at an unavailable time"}
                    {administration.data.access_locked_by_display_name ? ` by ${administration.data.access_locked_by_display_name}` : ""}. Reason: {administration.data.access_lock_reason ?? "Recorded in audit history"}. Old sessions remain revoked after unlock.
                  </Alert>
                )}
                {canAdministerIdentity && administration.data.user_id && ["ACTIVE", "LOCKED"].includes(administration.data.access_status) && (
                  <div className="mt-4 rounded-lg border border-stroke bg-surface-subtle p-3">
                    <h5 className="text-sm font-semibold">Emergency access control</h5>
                    <p className="mt-1 text-sm text-content-muted">Locking access is separate from employment status and preserves Employee and operating history.</p>
                    <Button className="mt-3" variant={administration.data.access_status === "ACTIVE" ? "destructive" : "secondary"} onClick={() => { setAccessLockReason(""); setConfirmAccessLock(true); }}>
                      {administration.data.access_status === "ACTIVE" ? "Lock Access" : "Unlock Access"}
                    </Button>
                    {accessLock.isError && <Alert className="mt-3" variant="danger">The access state was not changed. Refresh current authority and try again.</Alert>}
                  </div>
                )}
                {canAdministerIdentity && administration.data.user_id && administration.data.access_status === "ACTIVE" && (
                  <div className="mt-4 rounded-lg bg-surface-subtle p-3">
                    <h5 className="text-sm font-semibold">Account Access</h5>
                    <p className="mt-1 text-sm text-content-muted">
                      Password reset: {passwordReset.query.data?.state.replaceAll("_", " ") ?? "Loading"}
                    </p>
                    <Button className="mt-3" variant="secondary" onClick={() => setConfirmPasswordReset(true)} disabled={passwordReset.mutation.isPending}>
                      Send Password Reset
                    </Button>
                    {passwordReset.mutation.isError && <Alert className="mt-3" variant="danger">The reset was not queued. Refresh employee authority and try again.</Alert>}
                  </div>
                )}
                <div className="mt-4 grid gap-4 lg:grid-cols-2">
                  <div>
                    <h5 className="text-sm font-semibold">Role bundles</h5>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {administration.data.role_codes.map((code) => (
                        <Badge key={code} variant="neutral">
                          {code.replaceAll("_", " ")}
                        </Badge>
                      ))}
                      {administration.data.role_codes.length === 0 && <span className="text-sm text-content-muted">No active role assignment.</span>}
                    </div>
                  </div>
                  <div>
                    <h5 className="text-sm font-semibold">Branch access</h5>
                    <p className="mt-2 break-words text-sm text-content-muted">{administration.data.branch_ids.length ? administration.data.branch_ids.map(branchName).join(", ") : "No explicit Branch access."}</p>
                  </div>
                </div>
                {administration.data.membership_id && (canManageMembership || canManageBranches) && (
                  <div className="mt-4 grid gap-3 rounded-lg bg-surface-subtle p-3 lg:grid-cols-3">
                    {canManageMembership && (
                      <div>
                        <h5 className="text-sm font-semibold">Membership state</h5>
                        <button
                          type="button"
                          disabled={accessMutation.isPending}
                          onClick={() =>
                            accessMutation.mutate({
                              type: "membership",
                              membershipId: administration.data.membership_id!,
                              status: administration.data.membership_status === "active" ? "suspended" : "active",
                            })
                          }
                          className="mt-2 rounded-lg border border-stroke px-3 py-2 text-sm font-medium"
                        >
                          {administration.data.membership_status === "active" ? "Suspend access" : "Reactivate access"}
                        </button>
                      </div>
                    )}
                    {canManageBranches && (
                      <form
                        onSubmit={(event) => {
                          event.preventDefault();
                          if (selectedBranchGrant)
                            accessMutation.mutate({
                              type: "branch",
                              membershipId: administration.data.membership_id!,
                              branchId: selectedBranchGrant,
                              enabled: !administration.data.branch_ids.includes(selectedBranchGrant),
                            });
                        }}
                      >
                        <label className="text-sm font-semibold" htmlFor="employee-branch-grant">
                          Branch access
                        </label>
                        <select id="employee-branch-grant" className="mt-2 min-h-10 w-full rounded-lg border border-stroke bg-surface px-2" value={selectedBranchGrant} onChange={(event) => setSelectedBranchGrant(event.target.value)}>
                          <option value="">Select Branch</option>
                          {(activeCompany?.branches ?? []).map((branch) => (
                            <option key={branch.id} value={branch.id}>
                              {branch.name}
                              {administration.data.branch_ids.includes(branch.id) ? " (granted)" : ""}
                            </option>
                          ))}
                        </select>
                        <button type="submit" disabled={!selectedBranchGrant || accessMutation.isPending} className="mt-2 rounded-lg border border-stroke px-3 py-2 text-sm font-medium">
                          {administration.data.branch_ids.includes(selectedBranchGrant) ? "Remove grant" : "Grant Branch"}
                        </button>
                      </form>
                    )}
                  </div>
                )}
                {accessMutation.isError && (
                  <div className="mt-3">
                    <Alert variant="danger" title="Access change not applied">
                      The change conflicts with current authority or requires a permitted administrator. Refresh and review the Employee state.
                    </Alert>
                  </div>
                )}
                {canAdministerIdentity && (
                  <section className="mt-5 rounded-lg border border-stroke bg-surface-subtle p-4" aria-label="Platform Access">
                    <h5 className="font-semibold">Platform Access</h5>
                    <p className="mt-1 text-sm text-content-muted">Functional access controls what this Employee may do in TwelveHats. It does not change employment, compensation, demonstrated skill, or work history.</p>
                    {functionalAccess.query.isLoading && <Spinner label="Loading functional access" />}
                    <ul className="mt-3 space-y-2">
                      {(functionalAccess.query.data ?? []).filter((item) => item.revoked_at === null).map((item) => (
                        <li key={item.assignment_id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-stroke bg-surface p-3 text-sm">
                          <span><strong>{item.functional_area.replaceAll("_", " ")}</strong> → {item.access_level.replaceAll("_", " ")} · {item.lifecycle_state.toLocaleLowerCase()}{item.expires_at ? ` until ${new Date(item.expires_at).toLocaleString()}` : " until removed"}</span>
                          {item.effective && <Button type="button" variant="outline" onClick={() => functionalAccess.revoke.mutate({ assignmentId: item.assignment_id, reason: "Owner removed functional access" })}>Remove</Button>}
                        </li>
                      ))}
                    </ul>
                    <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={(event) => {
                      event.preventDefault();
                      functionalAccess.grant.mutate({
                        functional_area: functionalArea,
                        access_level: functionalLevel,
                        effective_at: functionalEffective ? new Date(functionalEffective).toISOString() : new Date().toISOString(),
                        expires_at: functionalExpires ? new Date(functionalExpires).toISOString() : null,
                        reason: functionalReason.trim(),
                      });
                    }}>
                      <label className="text-sm">Functional area<Select className="mt-1" value={functionalArea} onChange={(event) => { const area = event.target.value; setFunctionalArea(area); setFunctionalLevel(area === "FIELD_OPERATIONS" ? "TECHNICIAN" : area === "CUSTOMER_SERVICE" ? "CSR" : area === "DISPATCH" ? "DISPATCHER" : "READ"); }}><option value="FIELD_OPERATIONS">Field Operations</option><option value="CUSTOMER_SERVICE">Customer Service</option><option value="DISPATCH">Dispatch</option><option value="REPORTING_ECONOMICS">Reporting / Economics</option></Select></label>
                      <label className="text-sm">Access level<Select className="mt-1" value={functionalLevel} onChange={(event) => setFunctionalLevel(event.target.value)}>{functionalArea === "FIELD_OPERATIONS" && <option value="TECHNICIAN">Technician</option>}{functionalArea === "CUSTOMER_SERVICE" && <option value="CSR">CSR</option>}{functionalArea === "DISPATCH" && <option value="DISPATCHER">Dispatcher</option>}{functionalArea === "REPORTING_ECONOMICS" && <option value="READ">Read</option>}</Select></label>
                      <label className="text-sm">Effective from (blank = now)<Input className="mt-1" type="datetime-local" value={functionalEffective} onChange={(event) => setFunctionalEffective(event.target.value)} /></label>
                      <label className="text-sm">Expires (blank = until removed)<Input className="mt-1" type="datetime-local" value={functionalExpires} onChange={(event) => setFunctionalExpires(event.target.value)} /></label>
                      <label className="text-sm sm:col-span-2">Reason<Input required minLength={3} className="mt-1" value={functionalReason} onChange={(event) => setFunctionalReason(event.target.value)} placeholder="Temporary office coverage" /></label>
                      <Button className="sm:col-span-2" type="submit" disabled={functionalReason.trim().length < 3 || functionalAccess.grant.isPending}>Apply functional access</Button>
                    </form>
                    {(functionalAccess.grant.isError || functionalAccess.revoke.isError) && <Alert className="mt-3" variant="danger">Functional access was not changed. Review canonical roles, dates, and current Company authority.</Alert>}
                  </section>
                )}
                {administration.data.mobile_readiness_blockers.length > 0 && (
                  <Alert variant="warning" title="Mobile readiness blockers">
                    <ReadinessBlockers blockers={administration.data.mobile_readiness_blockers} />
                  </Alert>
                )}
                <div className="mt-5">
                  <h5 className="font-semibold">Effective permission explanation</h5>
                  <p className="mt-1 text-sm text-content-muted">Permissions are grouped by business area and derived from active roles. Own-data permissions never authorize another Employee identity.</p>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    {Object.entries(permissionAreas).map(([area, items]) => (
                      <section key={area} className="rounded-lg bg-surface-subtle p-3">
                        <h6 className="font-semibold">{area}</h6>
                        <ul className="mt-2 space-y-2">
                          {items.map((permission) => (
                            <li key={permission.code} className="text-sm">
                              <span className="font-medium">{permission.name}</span>
                              <span className="block text-xs text-content-muted">
                                {permission.authority.replaceAll("_", " ")} · {permission.branch_scoped ? "Branch scoped" : "Company scoped"} · {permission.role_codes.join(", ")}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </section>
                    ))}
                  </div>
                </div>
              </section>
            )}
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <section className="rounded-xl border border-stroke p-4">
                <h4 className="flex items-center gap-2 font-semibold">
                  <UserRoundCheck size={17} />
                  Demonstrated capability / evidence
                </h4>
                <div className="mt-3 space-y-2">
                  {detail.data.capabilities.map((item) => (
                    <p key={item.code} className="text-sm">
                      <strong>{item.display_name}</strong> · {item.proficiency}
                    </p>
                  ))}
                  {detail.data.capabilities.length === 0 && <p className="text-sm text-content-muted">Insufficient demonstrated evidence. This does not by itself block ordinary technician assignment.</p>}
                </div>
              </section>
              <section className="rounded-xl border border-stroke p-4">
                <h4 className="flex items-center gap-2 font-semibold">
                  <Languages size={17} />
                  Languages
                </h4>
                <div className="mt-3 space-y-2">
                  {detail.data.languages.map((item) => (
                    <p key={item.code} className="text-sm">
                      <strong>{item.english_name}</strong> · {item.spoken_proficiency}
                      {item.customer_facing_eligible ? " · customer-facing" : ""}
                    </p>
                  ))}
                  {detail.data.languages.length === 0 && <p className="text-sm text-content-muted">No explicit language evidence.</p>}
                </div>
              </section>
              <section className="rounded-xl border border-stroke p-4 md:col-span-2">
                <h4 className="flex items-center gap-2 font-semibold">
                  <Award size={17} />
                  Certifications
                </h4>
                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  {detail.data.certifications.map((item) => (
                    <div key={`${item.code}-${item.credential_reference}`} className="rounded-lg bg-surface-subtle p-3 text-sm">
                      <div className="flex justify-between gap-3">
                        <strong>{item.display_name}</strong>
                        <Badge variant="neutral">{item.status}</Badge>
                      </div>
                      <p className="mt-1 text-xs text-content-muted">
                        Evidence {item.credential_reference}
                        {item.expires_on ? ` · expires ${item.expires_on}` : " · no expiration recorded"}
                      </p>
                    </div>
                  ))}
                  {detail.data.certifications.length === 0 && <p className="text-sm text-content-muted">No certification evidence.</p>}
                </div>
              </section>
              <section className="rounded-xl border border-stroke p-4">
                <h4 className="flex items-center gap-2 font-semibold">
                  <ShieldCheck size={17} />
                  Branch authority
                </h4>
                <div className="mt-3 space-y-2">
                  {detail.data.branches.map((item) => (
                    <p key={item.branch_id} className="break-all text-sm">
                      {item.branch_id} · {item.status}
                    </p>
                  ))}
                  {detail.data.branches.length === 0 && <p className="text-sm text-content-muted">Home Branch only or no explicit eligibility evidence.</p>}
                </div>
              </section>
              <section className="rounded-xl border border-stroke p-4">
                <h4 className="font-semibold">Restrictions and equipment</h4>
                <p className="mt-3 text-sm text-content-muted">{detail.data.work_restrictions.length ? detail.data.work_restrictions.join(", ") : "No active work restriction evidence."}</p>
                <p className="mt-2 text-sm text-content-muted">{detail.data.equipment_capabilities.length ? detail.data.equipment_capabilities.map((item) => item.display_name).join(", ") : "No equipment capability evidence."}</p>
              </section>
              <section className="rounded-xl border border-stroke p-4 md:col-span-2">
                <h4 className="font-semibold">Schedule / Availability</h4>
                <p className="mt-1 text-sm text-content-muted">Normal availability inherits the home Branch schedule within active employment. Employee-specific records below are overrides or exceptions; Branch hours are not copied to the Employee.</p>
                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  {detail.data.availability.map((item) => (
                    <div key={`${item.branch_id}-${item.start_at}-${item.end_at}`} className="rounded-lg bg-surface-subtle p-3 text-sm">
                      <div className="flex justify-between gap-3">
                        <strong>{item.status}</strong>
                        <span className="text-xs text-content-muted">{item.source}</span>
                      </div>
                      <p className="mt-1 text-xs text-content-muted">
                        {new Date(item.start_at).toLocaleString()} – {new Date(item.end_at).toLocaleString()}
                      </p>
                    </div>
                  ))}
                  {detail.data.availability.length === 0 && <p className="text-sm text-content-muted">No Employee-specific exception or override. The active employment envelope and Branch schedule apply.</p>}
                </div>
              </section>
            </div>
              </div>
            </details>}
      </Card>
        )}
      {pendingPermissionNavigation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-labelledby="unsaved-permission-title">
          <div className="w-full max-w-md rounded-2xl border border-stroke bg-surface p-5 shadow-2xl">
            <h3 id="unsaved-permission-title" className="text-lg font-semibold">You have unsaved permission changes.</h3>
            <p className="mt-2 text-sm text-content-muted">Save them before leaving, discard the draft, or stay on this employee.</p>
            <div className="mt-5 flex flex-wrap justify-end gap-2"><Button variant="outline" onClick={() => setPendingPermissionNavigation(null)}>Stay</Button><Button variant="outline" onClick={() => { const navigate = pendingPermissionNavigation; setPendingPermissionNavigation(null); cancelPermissionDraft(); navigate?.(); }}>Discard</Button><Button variant="primary" disabled={permissionUpdate.isPending} onClick={savePermissionDraft}>Save</Button></div>
          </div>
        </div>
      )}
      {confirmPasswordReset && administration.data?.user_id && (
        <ConfirmationDialog
          title="Send password reset?"
          description={`ACP will send a single-use, expiring reset link to ${administration.data.login_email ?? "this employee's login email"}.`}
          confirmLabel="Send Password Reset"
          pending={passwordReset.mutation.isPending}
          onCancel={() => setConfirmPasswordReset(false)}
          onConfirm={() => passwordReset.mutation.mutate(undefined, { onSuccess: () => setConfirmPasswordReset(false) })}
        />
      )}
      {confirmDeactivation && detail.data && (
        <ConfirmationDialog
          title="Deactivate employee?"
          description="This ends active employment for scheduling and workforce readiness. Existing jobs, appointments, time records, and audit history remain preserved. It does not perform an emergency access lock."
          confirmLabel="Deactivate Employee"
          destructive
          pending={deactivation.isPending}
          onCancel={() => setConfirmDeactivation(false)}
          onConfirm={() => {
            if (deactivationReason.trim().length < 3 || !deactivationDate) return;
            deactivation.mutate(
              { effective_date: deactivationDate, reason: deactivationReason.trim() },
              { onSuccess: () => setConfirmDeactivation(false) },
            );
          }}
        >
          <div className="space-y-3">
            <label className="block text-sm font-medium" htmlFor="employee-deactivation-date">Effective date</label>
            <Input id="employee-deactivation-date" type="date" value={deactivationDate} onChange={(event) => setDeactivationDate(event.target.value)} required />
            <label className="block text-sm font-medium" htmlFor="employee-deactivation-reason">Reason</label>
            <Input id="employee-deactivation-reason" value={deactivationReason} onChange={(event) => setDeactivationReason(event.target.value)} minLength={3} maxLength={500} required placeholder="Reason for ending active employment" />
            {deactivationReason.trim().length > 0 && deactivationReason.trim().length < 3 && <p className="text-sm text-status-danger">Enter at least 3 characters.</p>}
            {deactivation.isError && <Alert variant="danger">The employee was not deactivated. Refresh the profile and verify current authority.</Alert>}
          </div>
        </ConfirmationDialog>
      )}
      {confirmAccessLock && administration.data?.user_id && administration.data.authorization_version && (
        <ConfirmationDialog
          title={administration.data.access_status === "LOCKED" ? "Unlock employee access?" : "Lock employee access immediately?"}
          description={administration.data.access_status === "LOCKED" ? "Future authentication will be restored, but every old web and Mobile session stays invalid. The employee must sign in again." : "This immediately blocks new authentication and revokes every active web, refresh, and Mobile session. Employment status and business history are unchanged."}
          confirmLabel={administration.data.access_status === "LOCKED" ? "Unlock Access" : "Lock Access"}
          destructive={administration.data.access_status !== "LOCKED"}
          pending={accessLock.isPending}
          onCancel={() => setConfirmAccessLock(false)}
          onConfirm={() => {
            if (accessLockReason.trim().length < 3) return;
            accessLock.mutate({
              locked: administration.data.access_status !== "LOCKED",
              reason: accessLockReason.trim(),
              expected_authorization_version: administration.data.authorization_version!,
            }, { onSuccess: () => setConfirmAccessLock(false) });
          }}
        >
          {administration.data.access_status !== "LOCKED" && (
            <Alert variant={administration.data.active_assignment_count + administration.data.today_future_assignment_count + administration.data.future_assignment_count > 0 ? "warning" : "information"} title="Assignment check">
              This employee currently has {administration.data.active_assignment_count + administration.data.today_future_assignment_count + administration.data.future_assignment_count} scheduled assignments ({administration.data.active_assignment_count} active now, {administration.data.today_future_assignment_count} later today, {administration.data.future_assignment_count} future). Assignments will not be canceled or reassigned. <Link className="font-semibold underline" to="/dispatch">Open Dispatch</Link> or <Link className="font-semibold underline" to="/scheduling">Scheduling</Link> to reassign work.
            </Alert>
          )}
          <label className="block font-medium" htmlFor="employee-access-lock-reason">Reason</label>
          <Input id="employee-access-lock-reason" value={accessLockReason} onChange={(event) => setAccessLockReason(event.target.value)} minLength={3} maxLength={500} required placeholder={administration.data.access_status === "LOCKED" ? "Reason access may be restored" : "Emergency security reason"} />
          {accessLockReason.trim().length > 0 && accessLockReason.trim().length < 3 && <p className="text-status-danger">Enter at least 3 characters.</p>}
        </ConfirmationDialog>
      )}
      </div>
    </div>
  );
}
