import type { LucideIcon } from "lucide-react";

export interface Breadcrumb {
  readonly label: string;
  readonly path?: string;
}

export interface WorkspaceMetadata {
  readonly pageTitle: string;
  readonly breadcrumbs: readonly Breadcrumb[];
  readonly helpTopic?: string;
  readonly aiContext?: string;
}

export interface ShellRouteHandle {
  readonly workspace: WorkspaceMetadata;
}

export type NavigationItemId =
  | "command-center"
  | "mission-control"
  | "customers"
  | "scheduling"
  | "dispatch"
  | "price-book"
  | "estimates"
  | "jobs"
  | "engineering"
  | "invoices"
  | "payments"
  | "revenue-cycle"
  | "accounts-payable"
  | "financial-reports"
  | "business-economics"
  | "payroll"
  | "inventory"
  | "purchasing"
  | "technician"
  | "workday"
  | "administration"
  | "employees"
  | "settings"
  | "dispatch-ai"
  | "customer-care-ai"
  | "accounting-ai"
  | "marketing-ai";

export interface NavigationItem {
  readonly id: NavigationItemId;
  readonly label: string;
  readonly path: string;
  readonly icon: LucideIcon;
  readonly availability: "available" | "coming-soon";
  readonly requiredPermission?: string;
}

export interface NavigationGroup {
  readonly id: string;
  readonly label: string;
  readonly items: readonly NavigationItem[];
}
