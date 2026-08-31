import { useState } from "react";
import { Link } from "react-router";
import { useHasPermission } from "../auth";
import {
  useEconomicsPolicyAdministration,
  useEconomicsResultLineage,
} from "../hooks/useBusinessEconomics";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Spinner,
} from "../ui";

const today = new Date().toISOString().slice(0, 10);
const monthStart = `${today.slice(0, 7)}-01`;
const label = (value: string) => value.replaceAll("_", " ");

export function EconomicsPolicyAdministrationRoute() {
  const canReadPolicy = useHasPermission("COMPANY_ECONOMICS_POLICY_READ");
  const canReadResults = useHasPermission("COMPANY_ECONOMICS_MEASUREMENT_READ");
  const [start, setStart] = useState(monthStart);
  const [end, setEnd] = useState(today);
  const [period, setPeriod] = useState({ start: monthStart, end: today });
  const [resultId, setResultId] = useState("");
  const administration = useEconomicsPolicyAdministration(
    period.start,
    period.end,
    canReadPolicy,
  );
  const lineage = useEconomicsResultLineage(
    resultId || null,
    canReadResults && Boolean(resultId),
  );

  if (!canReadPolicy)
    return (
      <Alert variant="danger">
        You are not authorized to inspect Economics policy administration.
      </Alert>
    );
  if (administration.isPending)
    return <Spinner label="Loading Economics policy readiness" />;
  if (administration.isError || !administration.data)
    return (
      <Alert variant="danger" title="Economics administration unavailable">
        <div className="space-y-3">
          <p>No policy or readiness state was inferred.</p>
          <Button
            variant="secondary"
            onClick={() => void administration.refetch()}
          >
            Retry administration
          </Button>
        </div>
      </Alert>
    );
  const value = administration.data;
  const decisions = value.policy_families.filter(
    (item) => item.state !== "CONFIGURED",
  );

  return (
    <div className="mx-auto max-w-7xl space-y-6 pb-12">
      <header>
        <p className="text-sm font-semibold text-action-primary">
          Owner administration
        </p>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">
          Economics readiness and policy
        </h1>
        <p className="mt-2 max-w-3xl text-content-muted">
          Inspect what ACP can measure, what evidence is incomplete, and which
          explicit owner decisions remain. This workspace is read-only.
        </p>
      </header>
      <Card>
        <CardContent className="pt-6">
          <form
            className="grid gap-3 sm:grid-cols-[1fr_1fr_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              setPeriod({ start, end });
            }}
          >
            <Input
              aria-label="Readiness start date"
              type="date"
              value={start}
              onChange={(event) => setStart(event.target.value)}
            />
            <Input
              aria-label="Readiness end date"
              type="date"
              value={end}
              onChange={(event) => setEnd(event.target.value)}
            />
            <Button type="submit">Inspect period</Button>
          </form>
        </CardContent>
      </Card>
      <section
        aria-label="Economics readiness"
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5"
      >
        {value.readiness.sources.map((source) => (
          <Card key={source.source}>
            <CardHeader>
              <CardTitle className="capitalize">
                {label(source.source)}
              </CardTitle>
              <CardDescription>
                {source.evidence_count} accepted result(s)
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="font-semibold">{label(source.state)}</p>
              <p className="mt-2 text-sm text-content-muted">
                {source.explanation}
              </p>
            </CardContent>
          </Card>
        ))}
      </section>
      <Alert
        variant={decisions.length ? "warning" : "success"}
        title={
          decisions.length
            ? `${decisions.length} policy decision(s) remain`
            : "Policy authority configured"
        }
      >
        {decisions.length
          ? "ACP has not selected real Company values. Review supported choices and required evidence before an authorized policy workflow records a decision."
          : "Every registered policy family has current selected authority."}
      </Alert>
      <section className="grid gap-4 lg:grid-cols-2">
        {value.policy_families.map((family) => (
          <Card key={family.family_key}>
            <CardHeader>
              <CardTitle>{family.title}</CardTitle>
              <CardDescription>
                {family.decision_id} · {label(family.state)}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                <strong>Current strategy:</strong>{" "}
                {family.current_strategy
                  ? label(family.current_strategy)
                  : "Unconfigured"}
              </p>
              <p>
                <strong>Supported choices:</strong>{" "}
                {family.supported_strategies.map(label).join(", ")}
              </p>
              <p>
                <strong>Required configuration:</strong>{" "}
                {family.required_parameter_keys.length
                  ? family.required_parameter_keys.map(label).join(", ")
                  : "No additional parameters"}
              </p>
              <p>
                <strong>Configured keys:</strong>{" "}
                {family.configured_parameter_keys.length
                  ? family.configured_parameter_keys.map(label).join(", ")
                  : "None"}
              </p>
              {family.policy_digest ? (
                <p className="break-all text-xs text-content-muted">
                  Policy digest {family.policy_digest}
                </p>
              ) : null}
            </CardContent>
          </Card>
        ))}
      </section>
      <Card>
        <CardHeader>
          <CardTitle>Policy version history</CardTitle>
          <CardDescription>
            Safe immutable authority metadata; no policy values or protected
            source data.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {value.policy_history.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-sm">
                <thead>
                  <tr className="text-left">
                    <th>Family</th>
                    <th>Version</th>
                    <th>State</th>
                    <th>Effective</th>
                    <th>Strategy</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {value.policy_history.map((item) => (
                    <tr className="border-b border-stroke" key={item.policy_id}>
                      <td className="py-3 capitalize">
                        {label(item.family_key)}
                      </td>
                      <td>{item.version}</td>
                      <td className="capitalize">{item.authority_state}</td>
                      <td>
                        {item.effective_start}
                        {item.effective_end ? ` – ${item.effective_end}` : ""}
                      </td>
                      <td>
                        {item.strategy
                          ? label(item.strategy)
                          : label(item.disposition)}
                      </td>
                      <td
                        className="max-w-48 truncate font-mono text-xs"
                        title={item.policy_digest}
                      >
                        {item.policy_digest}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-content-muted">
              No policy version has been accepted for this Company.
            </p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Immutable result history</CardTitle>
          <CardDescription>
            Enter a result identity from Business Economics to inspect its
            authorized Company/Branch lineage.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {canReadResults ? (
            <>
              <form
                className="flex flex-col gap-3 sm:flex-row"
                onSubmit={(event) => {
                  event.preventDefault();
                  setResultId(
                    new FormData(event.currentTarget)
                      .get("result_id")
                      ?.toString()
                      .trim() ?? "",
                  );
                }}
              >
                <Input
                  name="result_id"
                  aria-label="Economics result identity"
                  placeholder="Result UUID"
                />
                <Button type="submit">Inspect history</Button>
              </form>
              {resultId && lineage.isPending ? (
                <Spinner label="Loading result history" />
              ) : null}
              {resultId && (lineage.isError || !lineage.data) ? (
                <Alert variant="danger">
                  Result history is unavailable or outside your Company/Branch
                  authority.
                </Alert>
              ) : null}
              {lineage.data ? (
                <ol className="space-y-3">
                  {lineage.data.results.map((item) => (
                    <li
                      className="rounded border border-stroke p-3"
                      key={item.result_id}
                    >
                      <p className="font-semibold capitalize">
                        {item.authority_state} ·{" "}
                        {item.supersession_reason
                          ? label(item.supersession_reason)
                          : "original result"}
                      </p>
                      <p className="text-sm">
                        {item.period_start} – {item.period_end} ·{" "}
                        {item.currency}
                      </p>
                      <p className="break-all text-xs text-content-muted">
                        Result {item.result_digest}
                        <br />
                        Package {item.package_digest}
                        <br />
                        Computation {item.computation_digest}
                      </p>
                      {item.limitations.length ? (
                        <p className="mt-2 text-sm text-status-warning">
                          Limitations: {item.limitations.join("; ")}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ol>
              ) : null}
            </>
          ) : (
            <Alert variant="warning">
              Economics measurement-read authority is required to inspect result
              history.
            </Alert>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Interpretation layers</CardTitle>
          <CardDescription>
            Economics owns measured truth. Luminary interprets admitted
            evidence. LIA explains or proposes within read-only authority.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 sm:flex-row">
          <Link
            className="inline-flex min-h-11 items-center justify-center rounded-md bg-action-secondary px-ui-4 text-center text-body-s font-semibold text-content hover:brightness-110"
            to="/business-economics"
          >
            Open Economics results
          </Link>
          <Link
            className="inline-flex min-h-11 items-center justify-center rounded-md bg-action-secondary px-ui-4 text-center text-body-s font-semibold text-content hover:brightness-110"
            to="/luminary"
          >
            Open Luminary interpretation
          </Link>
          <Link
            className="inline-flex min-h-11 items-center justify-center rounded-md bg-action-primary px-ui-4 text-center text-body-s font-semibold text-content-inverse hover:bg-action-primary-hover"
            to="/lia"
          >
            Ask LIA
          </Link>
        </CardContent>
      </Card>
      <p className="break-all text-xs text-content-muted">
        Administration fingerprint {value.administration_fingerprint}
      </p>
    </div>
  );
}
