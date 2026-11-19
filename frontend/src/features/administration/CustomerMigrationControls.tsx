import { getOperatorApiError } from "../../api/errors";
import { useHasPermission } from "../../auth";
import {
  useCustomerCleanMajorityAdmission,
  useCustomerPopulationRefresh,
} from "../../hooks/useCustomers";
import { Alert, Badge, Button, Card, Spinner } from "../../ui";
import { useMigrationReadiness } from "./hooks";

/**
 * Customer source controls are deliberately kept out of the daily Customer
 * roster. They remain available to authorized administrators in Administration.
 */
export function CustomerMigrationControls() {
  const canAdminister = useHasPermission("COMPANY_ADMINISTER");
  const migration = useMigrationReadiness(canAdminister);
  const populationRefresh = useCustomerPopulationRefresh();
  const cleanMajorityAdmission = useCustomerCleanMajorityAdmission();
  const sourceCounts = (migration.data?.counts ?? []).filter((item) =>
    ["Customers", "Contacts", "Locations"].includes(item.domain),
  );
  const sourceProjectionPartial = sourceCounts.some((item) =>
    item.migrated !== item.source
    || item.held > 0
    || item.exception > 0
    || item.deferred > 0
    || item.unresolved > 0
    || item.delta !== 0,
  );

  if (!canAdminister) return null;

  return (
    <div className="space-y-ui-4" aria-label="Customer data import administration">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-ui-3">
          <div>
            <p className="text-body-s font-medium text-action-primary">Customer data import</p>
            <h2 className="mt-ui-1 text-heading-s">Source accounting and reconciliation</h2>
            <p className="mt-ui-2 max-w-3xl text-body-s text-content-muted">
              Administrator-only controls for source evidence, deterministic Customer admission,
              and held records. Daily Customer work stays in the Customers workspace.
            </p>
          </div>
          {migration.data && <Badge variant={migration.data.stale ? "warning" : "neutral"}>{migration.data.stale ? "Stale source projection" : migration.data.overall_status.replaceAll("_", " ")}</Badge>}
        </div>
        {migration.isLoading && <div className="mt-ui-4"><Spinner label="Loading source accounting" /></div>}
        {migration.isError && <div className="mt-ui-4"><Alert variant="warning" title="Source accounting unavailable" action={<Button type="button" variant="outline" onClick={() => void migration.refetch()}>Retry source accounting</Button>}>Customer work remains usable, but source completeness and freshness are unverified.</Alert></div>}
        {migration.data && <>
          <p className="mt-ui-3 text-body-s text-content-muted">Sealed source projection through {migration.data.historical_window.ends_on || "an unavailable date"}. This does not replace the live Customer roster.</p>
          {migration.data.stale && <Alert className="mt-ui-4" variant="warning" title="Source projection is stale">Do not treat this source population or as-of date as current completeness evidence.</Alert>}
          {sourceProjectionPartial && <Alert className="mt-ui-4" variant="information" title="Source population is partial">Held, exception, deferred, unresolved, and not-yet-admitted records remain outside Customer authority.</Alert>}
          <div className="mt-ui-4 grid gap-ui-3 sm:grid-cols-3">{sourceCounts.map((item) => <div key={item.domain} className="rounded-lg border border-stroke p-ui-3"><p className="font-semibold">{item.domain}</p><p className="mt-ui-1 text-body-s">{item.migrated.toLocaleString()} projected / {item.source.toLocaleString()} acquired source</p><p className="mt-ui-1 text-body-xs text-content-muted">{item.held.toLocaleString()} held · {item.exception.toLocaleString()} exception · {item.deferred.toLocaleString()} deferred · {item.unresolved.toLocaleString()} unresolved · delta {item.delta.toLocaleString()}</p></div>)}</div>
        </>}
      </Card>

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-ui-3">
          <div>
            <p className="text-body-s font-medium text-action-primary">Customer source reconciliation</p>
            <h2 className="mt-ui-1 text-heading-s">Admit deterministic HCP Customers</h2>
            <p className="mt-ui-2 max-w-3xl text-body-s text-content-muted">Create or bind only Customers with exact provider identity and validated source evidence. Ambiguous or unmatched records remain held for review; this never performs a fuzzy merge.</p>
          </div>
          <div className="flex flex-wrap gap-ui-2">
            <Button type="button" variant="outline" loading={populationRefresh.isPending} onClick={() => populationRefresh.mutate()}>Refresh source classification</Button>
            <Button type="button" loading={cleanMajorityAdmission.isPending} loadingLabel="Customer admission is running" onClick={() => cleanMajorityAdmission.mutate()}>Admit deterministic Customers</Button>
          </div>
        </div>
        {populationRefresh.isError && (() => { const error = getOperatorApiError(populationRefresh.error, "Customer source reconciliation"); return <Alert className="mt-ui-4" variant="danger" title={error.title}>{error.message}</Alert>; })()}
        {populationRefresh.data && <Alert className="mt-ui-4" variant={populationRefresh.data.counts.ambiguous || populationRefresh.data.counts.unexplained ? "warning" : "success"} title="Source classification refreshed">{populationRefresh.data.counts.total.toLocaleString()} accepted source Customers · {populationRefresh.data.counts.bound.toLocaleString()} bound · {populationRefresh.data.counts.held.toLocaleString()} held · {populationRefresh.data.counts.ambiguous.toLocaleString()} ambiguous · {populationRefresh.data.counts.unexplained.toLocaleString()} unexplained. No Customer admission was performed.</Alert>}
        {cleanMajorityAdmission.isPending && <Alert className="mt-ui-4" variant="information" title="Deterministic admission is running">Keep this page open until the authoritative completion receipt appears. Do not submit again from another tab.</Alert>}
        {cleanMajorityAdmission.isError && (() => { const error = getOperatorApiError(cleanMajorityAdmission.error, "Customer admission"); return <Alert className="mt-ui-4" variant="danger" title={error.title}>{error.message} Do not submit again until source classification recovers.</Alert>; })()}
        {cleanMajorityAdmission.data && <>
          <Alert className="mt-ui-4" variant={cleanMajorityAdmission.data.quarantined || cleanMajorityAdmission.data.remaining_unexplained ? "warning" : "success"} title="Deterministic admission complete">{cleanMajorityAdmission.data.processed.toLocaleString()} processed · {cleanMajorityAdmission.data.admitted.toLocaleString()} created · {cleanMajorityAdmission.data.replayed.toLocaleString()} replayed · {cleanMajorityAdmission.data.quarantined.toLocaleString()} held or quarantined · {cleanMajorityAdmission.data.rejected.toLocaleString()} rejected · {cleanMajorityAdmission.data.provider_unavailable.toLocaleString()} provider unavailable · {cleanMajorityAdmission.data.remaining_unexplained.toLocaleString()} unexplained.</Alert>
          {cleanMajorityAdmission.data.quarantine_records.length > 0 && <section className="mt-ui-4 rounded-lg border border-status-warning/40 p-ui-4" aria-label="Customer admission review queue"><h3 className="font-semibold">Customer admission review</h3><p className="mt-ui-1 text-body-s text-content-muted">These source Customers remain outside native authority until the exact evidence is resolved.</p><ul className="mt-ui-3 space-y-ui-3">{cleanMajorityAdmission.data.quarantine_records.map((record) => <li key={record.source_customer_id}><p className="font-medium">Provider Customer {record.source_customer_id}</p><p className="text-body-s text-content-muted">{record.reason}</p><p className="text-body-xs text-content-muted">Reason: {record.reason_code.replaceAll("_", " ")}</p></li>)}</ul></section>}
        </>}
      </Card>
    </div>
  );
}
