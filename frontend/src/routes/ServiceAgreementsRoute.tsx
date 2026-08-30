import { useState, type FormEvent } from "react";
import { useHasPermission } from "../auth";
import {
  useAgreementMutations,
  useAgreementPlans,
  useAgreementWorkspace,
} from "../hooks/useServiceAgreements";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Spinner,
} from "../ui";

export function ServiceAgreementsRoute() {
  const canRead = useHasPermission("COMPANY_SERVICE_AGREEMENT_READ"),
    canManage = useHasPermission("COMPANY_SERVICE_AGREEMENT_MANAGE"),
    canAdmin = useHasPermission("COMPANY_SERVICE_AGREEMENT_PLAN_MANAGE");
  const workspace = useAgreementWorkspace(),
    plans = useAgreementPlans(),
    mutations = useAgreementMutations();
  const [query, setQuery] = useState("");
  const [enroll, setEnroll] = useState({
    branch_id: "",
    customer_id: "",
    plan_id: "",
    service_location_ids: "",
    start_date: "",
    end_date: "",
  });
  if (!canRead)
    return (
      <Alert variant="danger">
        You are not authorized to view Service Agreements.
      </Alert>
    );
  if (workspace.isPending || plans.isPending)
    return <Spinner label="Loading Service Agreements" />;
  if (workspace.isError || plans.isError)
    return (
      <Alert variant="danger">
        Service Agreement authority could not be loaded.
      </Alert>
    );
  const rows = (workspace.data?.agreements ?? []).filter(
    (x) =>
      !query ||
      x.agreement_number.toLowerCase().includes(query.toLowerCase()) ||
      x.customer_id.includes(query),
  );
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    await mutations.enroll.mutateAsync({
      ...enroll,
      service_location_ids: enroll.service_location_ids
        .split(",")
        .map((x) => x.trim())
        .filter(Boolean),
      idempotency_key: crypto.randomUUID(),
    });
  };
  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-12">
      <header>
        <p className="text-sm font-semibold text-action-primary">
          Customer Operations
        </p>
        <h1 className="text-3xl font-bold">Service Agreements</h1>
        <p className="text-content-muted">
          Provider-neutral plans, covered locations, recurring service
          obligations, renewal, and billing readiness.
        </p>
      </header>
      <div className="grid gap-3 sm:grid-cols-4">
        <Metric label="Active" value={workspace.data?.active_count ?? 0} />
        <Metric
          label="Service due"
          value={workspace.data?.service_due_count ?? 0}
        />
        <Metric
          label="Renewal review"
          value={workspace.data?.renewal_pending_count ?? 0}
        />
        <Metric
          label="Billing unconfigured"
          value={workspace.data?.billing_unconfigured_count ?? 0}
        />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Agreement population</CardTitle>
          <CardDescription>
            Billing readiness is evidence only; no Invoice or Payment is created
            here.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Input
            aria-label="Search Agreements"
            placeholder="Agreement number or Customer ID"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="mt-4 space-y-2">
            {rows.map((a) => (
              <div key={a.id} className="rounded-lg border border-stroke p-3">
                <div className="flex flex-wrap justify-between gap-2">
                  <strong>{a.agreement_number}</strong>
                  <Badge variant="neutral">{a.status}</Badge>
                </div>
                <p className="text-sm text-content-muted">
                  Customer {a.customer_id} · {a.start_date}–{a.end_date}
                </p>
                {canManage && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {a.status === "pending_activation" && (
                      <Button
                        onClick={() =>
                          void mutations.transition.mutateAsync({
                            id: a.id,
                            action: "activate",
                            input: {
                              expected_version: a.version,
                              idempotency_key: crypto.randomUUID(),
                            },
                          })
                        }
                      >
                        Activate
                      </Button>
                    )}
                    {a.status === "active" && (
                      <>
                        <Button
                          variant="secondary"
                          onClick={() =>
                            void mutations.generate.mutateAsync(a.id)
                          }
                        >
                          Generate service obligations
                        </Button>
                        <Button
                          variant="secondary"
                          onClick={() =>
                            void mutations.transition.mutateAsync({
                              id: a.id,
                              action: "renewal-review",
                              input: {
                                expected_version: a.version,
                                idempotency_key: crypto.randomUUID(),
                              },
                            })
                          }
                        >
                          Start renewal review
                        </Button>
                  <Button
                    variant="secondary"
                          onClick={() =>
                            void mutations.transition.mutateAsync({
                              id: a.id,
                              action: "cancel",
                              input: {
                                expected_version: a.version,
                                idempotency_key: crypto.randomUUID(),
                                reason: "operator_cancelled",
                              },
                            })
                          }
                        >
                          Cancel
                        </Button>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
            {!rows.length && (
              <p className="text-sm text-content-muted">No Agreements match.</p>
            )}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Service-due queue</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {workspace.data?.entitlements.map((e) => (
              <div
                key={e.id}
                className="flex flex-wrap justify-between rounded-lg border border-stroke p-3"
              >
                <span>
                  {e.service_category} · Location {e.service_location_id}
                </span>
                <span>
                  {e.eligible_from}–{e.eligible_to} · {e.status}
                </span>
              </div>
            ))}
            {!workspace.data?.entitlements.length && (
              <p className="text-sm text-content-muted">
                No generated service obligations.
              </p>
            )}
          </div>
        </CardContent>
      </Card>
      {canManage && (
        <Card>
          <CardHeader>
            <CardTitle>Enroll a Customer</CardTitle>
            <CardDescription>
              Only explicitly listed Service Locations are covered.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-3 sm:grid-cols-2"
              onSubmit={(e) => void submit(e)}
            >
              {Object.entries(enroll).map(([k, v]) => (
                <Input
                  key={k}
                  aria-label={k.replaceAll("_", " ")}
                  type={k.endsWith("date") ? "date" : "text"}
                  required
                  value={v}
                  onChange={(e) =>
                    setEnroll({ ...enroll, [k]: e.target.value })
                  }
                />
              ))}
              <Button type="submit" loading={mutations.enroll.isPending}>
                Create pending enrollment
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
      {canAdmin && (
        <Card>
          <CardHeader>
            <CardTitle>Plan Administration</CardTitle>
            <CardDescription>
              Production pricing, cadence, benefits, renewal, and cancellation
              remain visibly unconfigured until authorized.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {plans.data?.map((p) => (
              <div
                key={p.id}
                className="flex flex-wrap justify-between border-b border-stroke py-3"
              >
                <span>
                  {p.code} v{p.version} · {p.name}
                </span>
                <span>
                  {p.status} · {p.billing_cadence}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
function Metric({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-sm text-content-muted">{label}</p>
        <p className="text-2xl font-bold">{value}</p>
      </CardContent>
    </Card>
  );
}
