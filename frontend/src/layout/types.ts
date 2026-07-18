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
  | "mission-control"
  | "customers"
  | "dispatch"
  | "estimates"
  | "jobs"
  | "invoices"
  | "inventory"
  | "fleet"
  | "accounting"
  | "reports"
  | "administration";

export interface NavigationItem {
  readonly id: NavigationItemId;
  readonly label: string;
  readonly path: string;
  readonly icon: LucideIcon;
  readonly availability: "available" | "hidden";
  readonly requiredPermission?: string;
}
