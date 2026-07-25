interface KPIStatCardProps {
  label: string;
  value: string;
  detail: string;
}

export function KPIStatCard({
  label,
  value,
  detail,
}: KPIStatCardProps) {
  return (
    <article className="min-w-0 rounded-xl border border-stroke bg-surface p-ui-4 sm:p-ui-5">
      <p className="break-words text-sm text-content-muted">{label}</p>

      <p className="mt-2 break-words text-2xl font-bold text-content sm:mt-3 sm:text-3xl">
        {value}
      </p>

      <p className="mt-2 break-words text-xs text-content-muted">
        {detail}
      </p>
    </article>
  );
}
