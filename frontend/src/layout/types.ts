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
  | "lia"
  | "command-center"
  | "my-schedule"
  | "my-jobs"
  | "mission-control"
  | "factory-control"
  | "customers"
  | "pipeline"
  | "service-agreements"
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
  | "banking"
  | "qbo-migration"
  | "qbo-cutover"
  | "business-economics"
  | "economics-administration"
  | "luminary"
  | "payroll"
  | "inventory"
  | "assets"
  | "purchasing"
  | "technician"
  | "workday"
  | "administration"
  | "audit"
  | "data-quality"
  | "reports"
  | "operator-guide"
  | "owner-operations"
  | "employees"
  | "settings"
  | "dispatch-ai"
  | "customer-care-ai"
  | "accounting-ai"
  | "marketing-ai"
  | "marketing-provider-connections";

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
