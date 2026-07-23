import type { ShellRouteHandle } from "../layout";

export const missionControlHandle = {
  workspace: {
    pageTitle: "Mission Control",
    breadcrumbs: [{ label: "Mission Control" }],
    helpTopic: "mission-control",
    aiContext: "mission-control",
  },
} as const satisfies ShellRouteHandle;

export const customersHandle = {
  workspace: {
    pageTitle: "Customers",
    breadcrumbs: [{ label: "Customers" }],
    helpTopic: "customer-management",
    aiContext: "customers",
  },
} as const satisfies ShellRouteHandle;

export const jobsHandle = {
  workspace: { pageTitle: "Jobs", breadcrumbs: [{ label: "Jobs" }], helpTopic: "jobs", aiContext: "jobs" },
} as const satisfies ShellRouteHandle;

export const appointmentsHandle = {
  workspace: { pageTitle: "Appointment", breadcrumbs: [{ label: "Jobs", path: "/jobs" }, { label: "Appointment" }], helpTopic: "scheduling", aiContext: "scheduling" },
} as const satisfies ShellRouteHandle;

export const dispatchHandle = {
  workspace: { pageTitle: "Dispatch", breadcrumbs: [{ label: "Dispatch" }], helpTopic: "dispatch", aiContext: "dispatch" },
} as const satisfies ShellRouteHandle;

export const notFoundHandle = {
  workspace: {
    pageTitle: "Page not found",
    breadcrumbs: [{ label: "Page not found" }],
  },
} as const satisfies ShellRouteHandle;
