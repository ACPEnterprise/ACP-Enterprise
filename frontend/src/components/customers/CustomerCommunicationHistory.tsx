import { useQuery } from "@tanstack/react-query";
import { Mail, MessageSquareText } from "lucide-react";

import { listCustomerCommunicationHistory } from "../../api/communications";
import { getApiErrorMessage } from "../../api/errors";
import { Alert, Badge, Card } from "../../ui";

export function CustomerCommunicationHistory({ customerId }: { customerId: string }) {
  const history = useQuery({
    queryKey: ["customer-communication-history", customerId],
    queryFn: () => listCustomerCommunicationHistory(customerId),
  });

  return (
    <Card className="p-ui-4 sm:p-ui-6">
      <p className="text-sm text-action-primary">Customer engagement</p>
      <h3 className="mt-1 text-xl font-semibold">Communication history</h3>
      <p className="mt-2 text-sm text-content-muted">Provider-neutral delivery evidence only. This view cannot send or retry a message.</p>
      {history.isLoading && <p className="mt-4 text-sm text-content-muted">Loading communication history…</p>}
      {history.isError && <Alert variant="danger" title="Communication history unavailable">{getApiErrorMessage(history.error)}</Alert>}
      <div className="mt-5 space-y-3">
        {(history.data ?? []).map((item) => (
          <article key={item.id} className="flex min-w-0 gap-3 rounded-xl border border-stroke bg-surface-subtle p-4">
            {item.channel === "email" ? <Mail className="mt-0.5 shrink-0 text-action-primary" size={17} aria-hidden="true" /> : <MessageSquareText className="mt-0.5 shrink-0 text-action-primary" size={17} aria-hidden="true" />}
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">{item.communication_type.replaceAll("_", " ")}</p>
                <Badge variant="neutral">{item.state.replaceAll("_", " ")}</Badge>
              </div>
              <p className="mt-1 break-all text-sm text-content-muted">{item.channel.toUpperCase()} · {item.recipient}</p>
              <p className="mt-1 text-xs text-content-muted">Requested {new Date(item.created_at).toLocaleString()}{item.retry_count ? ` · ${item.retry_count} retries` : ""}</p>
              {item.terminal_failure && <p className="mt-2 text-xs font-medium text-status-danger">Terminal delivery failure requires authorized operator review.</p>}
            </div>
          </article>
        ))}
      </div>
      {history.isSuccess && history.data.length === 0 && <p className="mt-4 text-sm text-content-muted">No communication requests have been recorded for this Customer.</p>}
    </Card>
  );
}
