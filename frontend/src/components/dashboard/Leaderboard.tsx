export interface LeaderboardRow {
  id: string;
  name: string;
  primaryValue: string;
  secondaryValue?: string;
}

interface LeaderboardProps {
  title: string;
  subtitle?: string;
  rows: LeaderboardRow[];
  emptyMessage?: string;
}

export function Leaderboard({
  title,
  subtitle,
  rows,
  emptyMessage = "No leaderboard data is available yet.",
}: LeaderboardProps) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
      <div>
        <p className="text-sm font-medium text-blue-400">Performance</p>

        <h2 className="mt-1 text-xl font-semibold text-white">
          {title}
        </h2>

        {subtitle ? (
          <p className="mt-1 text-sm text-slate-400">{subtitle}</p>
        ) : null}
      </div>

      {rows.length === 0 ? (
        <div className="mt-6 rounded-xl border border-dashed border-slate-700 p-6 text-center">
          <p className="text-sm text-slate-400">{emptyMessage}</p>
        </div>
      ) : (
        <ol className="mt-6 space-y-3">
          {rows.map((row, index) => (
            <li
              key={row.id}
              className="flex items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-950/60 p-4"
            >
              <div className="flex min-w-0 items-center gap-4">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-800 text-sm font-bold text-slate-200">
                  {index + 1}
                </div>

                <div className="min-w-0">
                  <p className="truncate font-medium text-white">
                    {row.name}
                  </p>

                  {row.secondaryValue ? (
                    <p className="mt-1 text-sm text-slate-400">
                      {row.secondaryValue}
                    </p>
                  ) : null}
                </div>
              </div>

              <p className="shrink-0 font-semibold text-emerald-400">
                {row.primaryValue}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
