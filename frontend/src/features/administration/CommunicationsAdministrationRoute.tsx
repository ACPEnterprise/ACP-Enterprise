import { useQuery } from "@tanstack/react-query";
import { MailCheck, MessageSquareText, ShieldCheck } from "lucide-react";

import {
  getCommunicationOperationsSummary,
  getCommunicationsReadiness,
  listOperationalMessageCatalog,
} from "../../api/communications";
import { getApiErrorMessage } from "../../api/errors";
import { useAuth } from "../../auth";
import { Alert, Badge, Card, Spinner } from "../../ui";

function words(value: string) {
  return value.replaceAll("_", " ");
}

export function CommunicationsAdministrationRoute() {
  const { permissionCodes = [] } = useAuth();
  const canRead = permissionCodes.includes("COMPANY_COMMUNICATIONS_READ");
  const readiness = useQuery({
    queryKey: ["communications-readiness"],
    queryFn: getCommunicationsReadiness,
    enabled: canRead,
  });
  const catalog = useQuery({
    queryKey: ["communications-catalog"],
    queryFn: listOperationalMessageCatalog,
    enabled: canRead,
  });
  const summary = useQuery({
    queryKey: ["communications-operations-summary"],
    queryFn: getCommunicationOperationsSummary,
    enabled: canRead,
  });

  if (!canRead) {
    return <Alert variant="danger">Communications readiness requires Communications read permission.</Alert>;
  }
  if (readiness.isLoading || catalog.isLoading || summary.isLoading) {
    return <Spinner label="Loading Communications readiness" />;
  }
  if (readiness.isError || catalog.isError || summary.isError) {
    return (
      <Alert variant="danger" title="Communications readiness unavailable">
        {getApiErrorMessage(readiness.error ?? catalog.error ?? summary.error)}
      </Alert>
    );
  }

  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 pb-8">
      <header>
        <p className="text-sm text-action-primary">Administration</p>
        <h1 className="mt-1 text-2xl font-semibold">Communications readiness</h1>
        <p className="mt-2 max-w-3xl text-sm text-content-muted">
          Delivery is provider-neutral. Synthetic qualification never means real Email or SMS is ready.
        </p>
      </header>
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Channel readiness">
        {[
          ["Email", readiness.data!.email, MailCheck],
          ["SMS", readiness.data!.sms, MessageSquareText],
          ["Webhook", readiness.data!.webhook, ShieldCheck],
          ["Overall", readiness.data!.overall, ShieldCheck],
        ].map(([label, state, Icon]) => (
          <Card className="p-4" key={String(label)}>
            <Icon aria-hidden="true" size={18} />
            <h2 className="mt-3 font-semibold">{String(label)}</h2>
            <Badge variant={state === "READY" || String(state).endsWith("_READY") ? "success" : "warning"}>
              {words(String(state))}
            </Badge>
          </Card>
        ))}
      </section>
      <Alert variant="information">
        Real sender identity, domain verification, provider credentials, webhooks, and SMS registration remain external admission gates.
      </Alert>
      <section aria-labelledby="communications-operations-heading">
        <h2 id="communications-operations-heading" className="text-xl font-semibold">Delivery operations</h2>
        <p className="mt-1 text-sm text-content-muted">Provider acceptance remains pending until delivery evidence arrives.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {[
            ["Pending", summary.data!.pending],
            ["Pending delivery", summary.data!.accepted_pending_delivery],
            ["Delivered", summary.data!.delivered],
            ["Needs attention", summary.data!.needs_attention],
            ["Suppressed", summary.data!.suppressed],
          ].map(([label, count]) => (
            <Card className="p-4" key={String(label)}>
              <p className="text-sm text-content-muted">{String(label)}</p>
              <p className="mt-1 text-2xl font-semibold">{String(count)}</p>
            </Card>
          ))}
        </div>
      </section>
      <section>
        <h2 className="text-xl font-semibold">Governed operational catalog</h2>
        <p className="mt-1 text-sm text-content-muted">
          Each business domain owns the triggering fact. Communications owns recipient, channel, template, and delivery evidence.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {catalog.data!.map((item) => (
            <Card className="p-4" key={item.message_class}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h3 className="font-semibold">{words(item.message_class)}</h3>
                <Badge variant={item.policy_required ? "warning" : "neutral"}>
                  {item.policy_required ? "Policy required" : words(item.purpose)}
                </Badge>
              </div>
              <p className="mt-2 text-sm text-content-muted">Authority: {words(item.owner_domain)}</p>
              <p className="mt-1 text-sm">Purpose: {words(item.purpose)}</p>
              <p className="mt-1 text-sm">Channels: {item.allowed_channels.map(words).join(", ")}</p>
              <p className="mt-1 break-all text-xs text-content-muted">Template: {item.template_version}</p>
            </Card>
          ))}
        </div>
      </section>
    </main>
  );
}
