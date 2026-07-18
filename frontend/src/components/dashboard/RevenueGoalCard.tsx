interface RevenueGoalCardProps {
  title: string;
  goal: number;
  current: number;
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function RevenueGoalCard({
  title,
  goal,
  current,
}: RevenueGoalCardProps) {
  const percentage =
    goal > 0 ? Math.min(Math.round((current / goal) * 100), 100) : 0;

  const remaining = Math.max(goal - current, 0);

  return (
    <article className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
      <p className="text-sm text-blue-400">Revenue Goal</p>

      <h3 className="mt-1 text-xl font-semibold text-white">
        {title}
      </h3>

      <div className="mt-6 flex items-end justify-between gap-4">
        <div>
          <p className="text-sm text-slate-400">Booked</p>
          <p className="mt-1 text-3xl font-bold text-white">
            {formatCurrency(current)}
          </p>
        </div>

        <div className="text-right">
          <p className="text-sm text-slate-400">Goal</p>
          <p className="mt-1 text-lg font-semibold text-slate-200">
            {formatCurrency(goal)}
          </p>
        </div>
      </div>

      <div className="mt-6 h-3 overflow-hidden rounded-full bg-slate-800">
        <div
          className="h-full rounded-full bg-blue-600"
          style={{ width: `${percentage}%` }}
        />
      </div>

      <div className="mt-3 flex items-center justify-between text-sm">
        <span className="font-medium text-blue-400">
          {percentage}% complete
        </span>

        <span className="text-slate-400">
          {formatCurrency(remaining)} remaining
        </span>
      </div>
    </article>
  );
}
