import { useState } from "react";

import { EngineeringCommandList } from "../features/engineering-control/EngineeringCommandList";
import { useEngineeringCommands } from "../features/engineering-control/useEngineeringCommands";
import type { EngineeringApprovalState } from "../types/engineeringControl";
import { Alert, Button, EmptyState, Select, Spinner } from "../ui";

export function EngineeringRoute() {
  const [approvalState, setApprovalState] = useState<
    EngineeringApprovalState | undefined
  >();
  const [page, setPage] = useState(1);
  const query = useEngineeringCommands({ approvalState, page, pageSize: 20 });

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-medium text-blue-400">Engineering Control</p>
        <h2 className="mt-1 text-3xl font-bold">Engineering Commands</h2>
        <p className="mt-2 text-content-muted">
          Review owner-authorized instructions. Execution is not connected.
        </p>
      </header>
      <div className="max-w-sm">
        <label htmlFor="approval-filter" className="mb-2 block text-sm font-semibold">Approval status</label>
        <Select
          id="approval-filter"
          value={approvalState ?? ""}
          onChange={(event) => {
            setApprovalState(
              (event.target.value || undefined) as
                | EngineeringApprovalState
                | undefined,
            );
            setPage(1);
          }}
        >
          <option value="">All approval states</option>
          {["awaiting_approval", "approved", "rejected", "canceled", "expired"].map((state) => (
            <option key={state} value={state}>{state.replaceAll("_", " ")}</option>
          ))}
        </Select>
      </div>
      <section className="rounded-xl border border-stroke bg-surface" aria-label="Engineering Command results">
        {query.isLoading && <div className="flex min-h-40 items-center justify-center"><Spinner label="Loading Engineering Commands" /></div>}
        {query.isError && <div className="p-ui-5"><Alert variant="danger" announcement="assertive" title="Engineering Commands unavailable" action={<Button variant="outline" onClick={() => void query.refetch()}>Retry</Button>}>Your commands could not be loaded.</Alert></div>}
        {query.data?.items.length === 0 && <div className="p-ui-5"><EmptyState title="No Engineering Commands" description="No commands match this approval status." /></div>}
        {query.data && query.data.items.length > 0 && <EngineeringCommandList data={query.data} onPage={setPage} />}
      </section>
    </div>
  );
}
