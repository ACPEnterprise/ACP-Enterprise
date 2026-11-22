import { Link } from "react-router";

interface KPIStatCardProps {
  label: string;
  value: string;
  href: string;
}

export function KPIStatCard({
  label,
  value,
  href,
}: KPIStatCardProps) {
  return (
    <Link className="group block rounded-xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action-primary" to={href} aria-label={`${label}: ${value}`}>
      <article className="dashboard-card-border min-w-0 rounded-xl border bg-surface p-ui-4 transition group-hover:bg-surface-subtle sm:p-ui-5">
        <p className="break-words text-sm text-content-muted">{label}</p>
        <p className="mt-2 break-words text-2xl font-bold text-content sm:mt-3 sm:text-3xl">{value}</p>
      </article>
    </Link>
  );
}
