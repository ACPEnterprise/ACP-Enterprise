import type { ShellRouteHandle } from "../layout";

export const commandCenterHandle = {
  workspace: {
    pageTitle: "Command Center",
    breadcrumbs: [{ label: "Command Center" }],
    helpTopic: "command-center",
    aiContext: "command-center",
  },
} as const satisfies ShellRouteHandle;

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

export const customerDetailHandle = {
  workspace: {
    pageTitle: "Customer",
    breadcrumbs: [
      { label: "Customers", path: "/customers" },
      { label: "Customer" },
    ],
    helpTopic: "customer-management",
    aiContext: "customers",
  },
} as const satisfies ShellRouteHandle;

export const jobsHandle = {
  workspace: {
    pageTitle: "Jobs",
    breadcrumbs: [{ label: "Jobs" }],
    helpTopic: "jobs",
    aiContext: "jobs",
  },
} as const satisfies ShellRouteHandle;

export const appointmentsHandle = {
  workspace: {
    pageTitle: "Appointment",
    breadcrumbs: [
      { label: "Scheduling", path: "/scheduling" },
      { label: "Appointment" },
    ],
    helpTopic: "scheduling",
    aiContext: "scheduling",
  },
} as const satisfies ShellRouteHandle;

export const schedulingHandle = {
  workspace: {
    pageTitle: "Scheduling",
    breadcrumbs: [{ label: "Scheduling" }],
    helpTopic: "scheduling",
    aiContext: "scheduling",
  },
} as const satisfies ShellRouteHandle;

export const dispatchHandle = {
  workspace: {
    pageTitle: "Dispatch",
    breadcrumbs: [{ label: "Dispatch" }],
    helpTopic: "dispatch",
    aiContext: "dispatch",
  },
} as const satisfies ShellRouteHandle;

export const inventoryHandle = {
  workspace: {
    pageTitle: "Inventory",
    breadcrumbs: [{ label: "Inventory" }],
    helpTopic: "inventory",
    aiContext: "inventory",
  },
} as const satisfies ShellRouteHandle;

export const priceBookHandle = {
  workspace: {
    pageTitle: "Price Book",
    breadcrumbs: [{ label: "Price Book" }],
    helpTopic: "price-book",
    aiContext: "price-book",
  },
} as const satisfies ShellRouteHandle;

export const estimatesHandle = {
  workspace: {
    pageTitle: "Estimates",
    breadcrumbs: [{ label: "Estimates" }],
    helpTopic: "estimates",
    aiContext: "estimates",
  },
} as const satisfies ShellRouteHandle;

export const invoicesHandle = {
  workspace: {
    pageTitle: "Invoices",
    breadcrumbs: [{ label: "Invoices" }],
    helpTopic: "invoices",
    aiContext: "invoices",
  },
} as const satisfies ShellRouteHandle;

export const engineeringHandle = {
  workspace: {
    pageTitle: "Engineering",
    breadcrumbs: [{ label: "Engineering", path: "/engineering" }],
    helpTopic: "engineering-control",
    aiContext: "engineering-control",
  },
} as const satisfies ShellRouteHandle;

export const administrationHandle = {
  workspace: {
    pageTitle: "Administration",
    breadcrumbs: [{ label: "Administration" }],
    helpTopic: "role-administration",
    aiContext: "role-administration",
  },
} as const satisfies ShellRouteHandle;

export const notFoundHandle = {
  workspace: {
    pageTitle: "Page not found",
    breadcrumbs: [{ label: "Page not found" }],
  },
} as const satisfies ShellRouteHandle;
