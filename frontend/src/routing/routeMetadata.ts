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

export const notFoundHandle = {
  workspace: {
    pageTitle: "Page not found",
    breadcrumbs: [{ label: "Page not found" }],
  },
} as const satisfies ShellRouteHandle;
