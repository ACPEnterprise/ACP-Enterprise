import {
  Boxes,
  BriefcaseBusiness,
  Building2,
  ChartNoAxesCombined,
  CircleDollarSign,
  ClipboardList,
  FileChartColumn,
  FileText,
  LayoutDashboard,
  Settings,
  Users,
} from "lucide-react";

import type { NavigationItem } from "./types";

export const navigationCatalog = [
  { id: "mission-control", label: "Mission Control", path: "/mission-control", icon: LayoutDashboard, availability: "available" },
  { id: "customers", label: "Customers", path: "/customers", icon: Users, availability: "available" },
  { id: "dispatch", label: "Dispatch", path: "/dispatch", icon: ClipboardList, availability: "hidden" },
  { id: "estimates", label: "Estimates", path: "/estimates", icon: FileChartColumn, availability: "hidden" },
  { id: "jobs", label: "Jobs", path: "/jobs", icon: BriefcaseBusiness, availability: "hidden" },
  { id: "invoices", label: "Invoices", path: "/invoices", icon: FileText, availability: "hidden" },
  { id: "inventory", label: "Inventory", path: "/inventory", icon: Boxes, availability: "hidden" },
  { id: "fleet", label: "Fleet", path: "/fleet", icon: Building2, availability: "hidden" },
  { id: "accounting", label: "Accounting", path: "/accounting", icon: CircleDollarSign, availability: "hidden" },
  { id: "reports", label: "Reports", path: "/reports", icon: ChartNoAxesCombined, availability: "hidden" },
  { id: "administration", label: "Administration", path: "/administration", icon: Settings, availability: "hidden" },
] as const satisfies readonly NavigationItem[];

export const availableNavigation = navigationCatalog.filter(
  (item) => item.availability === "available",
);
