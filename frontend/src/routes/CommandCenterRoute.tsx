import {
  ArrowRight,
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  CircleAlert,
  ClipboardCheck,
  ShieldCheck,
  Users,
  Wrench,
} from "lucide-react";
import { Link } from "react-router";

import {
  CommandCenterPanel,
  ExecutiveMetricCard,
  IntegrationStateBadge,
  WorkforceRow,
} from "../components/command-center/CommandCenterPrimitives";
import { useAnalyticsSummary } from "../hooks/useAnalyticsSummary";
import { useJobs } from "../hooks/useJobs";

function formatCurrency(value: string | number): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "Data Unavailable";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(numeric);
}

function metricState(
  loading: boolean,
  error: boolean,
  value: string | number | undefined,
): { value?: string; state?: "awaiting-integration" | "no-data" } {
  if (loading) return { state: "awaiting-integration" };
  if (error || value === undefined) return { state: "no-data" };
  return { value: String(value) };
}

export function CommandCenterRoute() {
  const analytics = useAnalyticsSummary();
  const jobs = useJobs({ page: 1, pageSize: 1 });
  const revenue = analytics.data
    ? { value: formatCurrency(analytics.data.booked_revenue.value) }
    : metricState(analytics.isLoading, analytics.isError, undefined);
  const appointments = metricState(
    analytics.isLoading,
    analytics.isError,
    analytics.data?.appointments_booked.value,
  );
  const customers = metricState(
    analytics.isLoading,
    analytics.isError,
    analytics.data?.new_customers.value,
  );
  const jobCount = metricState(jobs.isLoading, jobs.isError, jobs.data?.total_count);

  return (
    <div className="space-y-ui-8">
      <header className="border-b border-stroke pb-ui-6">
        <div className="flex flex-wrap items-center justify-between gap-ui-3">
          <div>
            <p className="text-overline uppercase text-content-muted">Executive Operations</p>
            <h2 className="mt-ui-2 text-heading-xl text-content">Command Center</h2>
            <p className="mt-ui-2 max-w-3xl text-body text-content-secondary">
              A secure operating view for service-company leadership. Connected data is shown as
              reported; unavailable systems remain clearly identified.
            </p>
          </div>
          <IntegrationStateBadge state="available" />
        </div>
      </header>

      <section aria-labelledby="executive-overview-heading">
        <div className="mb-ui-4">
          <p className="text-overline uppercase text-content-muted">Today</p>
          <h2 id="executive-overview-heading" className="text-heading-m text-content">Executive Overview</h2>
        </div>
        <div className="grid gap-ui-4 sm:grid-cols-2 xl:grid-cols-4">
          <ExecutiveMetricCard
            label="Booked Revenue"
            detail="Reported by the connected analytics service."
            {...revenue}
          />
          <ExecutiveMetricCard
            label="Appointments"
            detail="Appointments booked in the current analytics period."
            {...appointments}
          />
          <ExecutiveMetricCard
            label="Jobs"
            detail="Authoritative Jobs currently visible to this Company."
            {...jobCount}
          />
          <ExecutiveMetricCard
            label="New Customers"
            detail="Customers created in the current analytics period."
            {...customers}
          />
        </div>
      </section>

      <div className="grid gap-ui-6 xl:grid-cols-[1.15fr_0.85fr]">
        <CommandCenterPanel
          title="Attention Center"
          description="Critical, approval, time-sensitive, and informational items will be consolidated here."
          action={<IntegrationStateBadge state="awaiting-integration" />}
        >
          <div className="flex items-start gap-ui-3 rounded-lg border border-dashed border-stroke p-ui-5">
            <CircleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-content-muted" />
            <div>
              <p className="font-semibold text-content">No critical issues requiring attention.</p>
              <p className="mt-ui-1 text-body-s text-content-muted">
                No connected attention source has reported a critical issue. Approval and incident
                aggregation are awaiting integration.
              </p>
            </div>
          </div>
        </CommandCenterPanel>

        <CommandCenterPanel
          title="Engineering Factory"
          description="Secure execution architecture is present; live provider operations are not asserted."
          action={<Link className="text-body-s font-semibold text-action-primary hover:underline" to="/engineering">Open workspace</Link>}
        >
          <dl className="grid grid-cols-2 gap-ui-3">
            {[
              ["Workers Online", "Not Connected"],
              ["Execution Providers", "Awaiting Integration"],
              ["Pending Reviews", "Awaiting Integration"],
              ["Completed Today", "No Data Available"],
              ["Success Rate", "No Data Available"],
              ["Current Activity", "Not Connected"],
            ].map(([label, value]) => (
              <div className="rounded-lg bg-surface-muted p-ui-3" key={label}>
                <dt className="text-caption text-content-muted">{label}</dt>
                <dd className="mt-ui-1 text-body-s font-semibold text-content">{value}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-ui-4 flex flex-wrap gap-ui-2">
            <IntegrationStateBadge state="available" />
            <IntegrationStateBadge state="not-connected" />
          </div>
        </CommandCenterPanel>
      </div>

      <div className="grid gap-ui-6 xl:grid-cols-2">
        <CommandCenterPanel
          title="AI Workforce"
          description="Provider-neutral workforce architecture with truthful integration states."
        >
          <ul>
            <WorkforceRow name="Engineering" description="Approval and transport architecture available." state="awaiting-integration" />
            <WorkforceRow name="Dispatcher" description="Operational assistant not implemented." state="coming-soon" />
            <WorkforceRow name="Scheduler" description="Scheduling assistant not implemented." state="coming-soon" />
            <WorkforceRow name="Customer Care" description="Customer-care assistant not implemented." state="coming-soon" />
            <WorkforceRow name="Accounting" description="Accounting assistant not implemented." state="coming-soon" />
            <WorkforceRow name="Marketing" description="Marketing assistant not implemented." state="coming-soon" />
          </ul>
        </CommandCenterPanel>

        <CommandCenterPanel
          title="Operations"
          description="Move directly into connected operational workspaces."
        >
          <div className="grid gap-ui-3 sm:grid-cols-2">
            {[
              { label: "Customers", detail: "Customer and service-location records", path: "/customers", icon: Users },
              { label: "Jobs", detail: "Work lifecycle and appointments", path: "/jobs", icon: BriefcaseBusiness },
              { label: "Dispatch", detail: "Existing operational dispatch workspace", path: "/dispatch", icon: CalendarDays },
            ].map(({ label, detail, path, icon: Icon }) => (
              <Link
                className="group flex min-h-28 flex-col justify-between rounded-lg border border-stroke p-ui-4 transition-colors hover:border-stroke-strong hover:bg-surface-muted motion-reduce:transition-none"
                key={path}
                to={path}
              >
                <div className="flex items-center gap-ui-2">
                  <Icon aria-hidden="true" className="size-5 text-action-primary" />
                  <span className="font-semibold text-content">{label}</span>
                </div>
                <span className="mt-ui-3 flex items-end justify-between gap-ui-2 text-body-s text-content-muted">
                  {detail}
                  <ArrowRight aria-hidden="true" className="size-4 shrink-0 transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none" />
                </span>
              </Link>
            ))}
            <div className="flex min-h-28 flex-col justify-between rounded-lg border border-dashed border-stroke p-ui-4">
              <div className="flex items-center gap-ui-2">
                <ClipboardCheck aria-hidden="true" className="size-5 text-content-muted" />
                <span className="font-semibold text-content">Estimates & Invoices</span>
              </div>
              <IntegrationStateBadge state="coming-soon" />
            </div>
          </div>
        </CommandCenterPanel>
      </div>

      <section aria-label="ACP Enterprise product principles" className="grid gap-ui-4 border-y border-stroke py-ui-6 md:grid-cols-3">
        {[
          { icon: Building2, title: "Built in America", detail: "A restrained industrial product identity." },
          { icon: ShieldCheck, title: "Secure by Design", detail: "Clear authority, tenant, and integration boundaries." },
          { icon: Wrench, title: "Built for Service Companies", detail: "Operational workflows remain central to the experience." },
        ].map(({ icon: Icon, title, detail }) => (
          <article className="flex gap-ui-3" key={title}>
            <Icon aria-hidden="true" className="size-5 shrink-0 text-accent" />
            <div>
              <h2 className="font-semibold text-content">{title}</h2>
              <p className="mt-ui-1 text-body-s text-content-muted">{detail}</p>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
