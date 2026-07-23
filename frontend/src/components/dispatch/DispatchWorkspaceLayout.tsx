import type { ReactNode } from "react";

export function DispatchWorkspaceLayout({ appointments, jobs, workforce }: { readonly appointments: ReactNode; readonly jobs: ReactNode; readonly workforce?: ReactNode }) {
  return <div className="grid gap-6 xl:grid-cols-2">
    {appointments}
    {jobs}
    {workforce && <aside aria-label="Workforce recommendations" className="xl:col-span-2">{workforce}</aside>}
  </div>;
}
