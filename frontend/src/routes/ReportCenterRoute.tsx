import { Link } from "react-router";
import { BarChart3, BriefcaseBusiness, Boxes, CreditCard, FileChartColumn, Users } from "lucide-react";
import { Card } from "../ui";

const groups = [
  { title: "Operations", icon: BriefcaseBusiness, items: [["Jobs", "/jobs"], ["Scheduling", "/scheduling"], ["Dispatch", "/dispatch"], ["Revenue cycle", "/revenue-cycle"]] },
  { title: "Sales", icon: FileChartColumn, items: [["Estimate pipeline", "/estimates"], ["Invoices", "/invoices"], ["Payments", "/payments"]] },
  { title: "Finance", icon: CreditCard, items: [["Financial reports", "/financial-reports"], ["Accounts Payable", "/accounts-payable"], ["Business Economics", "/business-economics"]] },
  { title: "Supply chain", icon: Boxes, items: [["Purchasing", "/purchasing"], ["Inventory", "/inventory"]] },
  { title: "Workforce", icon: Users, items: [["Employee readiness", "/employees"], ["Payroll reporting", "/payroll"]] },
] as const;

export function ReportCenterRoute() {
  return <div className="space-y-6"><header><p className="text-sm font-medium text-action-primary">Authoritative projections</p><h2 className="mt-1 text-2xl font-bold sm:text-3xl">Report Center</h2><p className="mt-2 text-content-muted">Navigate existing domain-owned reporting without creating a second analytics or financial truth engine.</p></header><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{groups.map((group) => <Card key={group.title} className="p-5"><h3 className="flex items-center gap-2 text-lg font-semibold"><group.icon size={18}/>{group.title}</h3><nav aria-label={`${group.title} reports`} className="mt-4 space-y-2">{group.items.map(([label, path]) => <Link key={path} to={path} className="flex min-h-11 items-center justify-between rounded-lg border border-stroke px-3 text-sm font-medium hover:bg-surface-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus"><span>{label}</span><BarChart3 size={16} aria-hidden="true"/></Link>)}</nav></Card>)}</div></div>;
}
