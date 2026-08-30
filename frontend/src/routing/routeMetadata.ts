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

export const technicianHandle = {
  workspace: {
    pageTitle: "My day",
    breadcrumbs: [{ label: "My day" }],
    helpTopic: "technician-itinerary",
    aiContext: "technician-itinerary",
  },
} as const satisfies ShellRouteHandle;

export const workdayHandle = {
  workspace: {
    pageTitle: "My time clock",
    breadcrumbs: [{ label: "My time clock" }],
    helpTopic: "workday-time",
    aiContext: "workday-time",
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

export const purchasingHandle = {
  workspace: {
    pageTitle: "Purchasing",
    breadcrumbs: [{ label: "Purchasing" }],
    helpTopic: "purchasing",
    aiContext: "purchasing",
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

export const paymentsHandle = {
  workspace: { pageTitle: "Payments", breadcrumbs: [{ label: "Payments" }], helpTopic: "payments", aiContext: "payments" },
} as const satisfies ShellRouteHandle;

export const revenueCycleHandle = {
  workspace: {
    pageTitle: "Revenue cycle",
    breadcrumbs: [{ label: "Revenue cycle" }],
    helpTopic: "revenue-cycle",
    aiContext: "revenue-cycle",
  },
} as const satisfies ShellRouteHandle;

export const accountsPayableHandle = {
  workspace: { pageTitle: "Accounts Payable", breadcrumbs: [{ label: "Accounts Payable" }], helpTopic: "accounts-payable", aiContext: "accounts-payable" },
} as const satisfies ShellRouteHandle;

export const financialReportsHandle = {
  workspace: { pageTitle: "Financial Reports", breadcrumbs: [{ label: "Financial Reports" }], helpTopic: "financial-reporting", aiContext: "financial-reporting" },
} as const satisfies ShellRouteHandle;

export const businessEconomicsHandle = {
  workspace: { pageTitle: "Business Economics", breadcrumbs: [{ label: "Business Economics" }], helpTopic: "business-economics", aiContext: "business-economics" },
} as const satisfies ShellRouteHandle;

export const payrollHandle = {
  workspace: { pageTitle: "Payroll Administration", breadcrumbs: [{ label: "Payroll" }], helpTopic: "payroll-administration", aiContext: "payroll-administration" },
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

export const auditHandle = {
  workspace: { pageTitle: "Audit history", breadcrumbs: [{ label: "Audit history" }], helpTopic: "audit-history" },
} as const satisfies ShellRouteHandle;

export const reportsHandle = {
  workspace: { pageTitle: "Report Center", breadcrumbs: [{ label: "Report Center" }], helpTopic: "report-center" },
} as const satisfies ShellRouteHandle;

export const operatorGuideHandle = {
  workspace: { pageTitle: "Operator guide", breadcrumbs: [{ label: "Operator guide" }], helpTopic: "operator-guide" },
} as const satisfies ShellRouteHandle;

export const notFoundHandle = {
  workspace: {
    pageTitle: "Page not found",
    breadcrumbs: [{ label: "Page not found" }],
  },
} as const satisfies ShellRouteHandle;
