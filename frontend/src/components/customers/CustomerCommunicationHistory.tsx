import { useQuery } from "@tanstack/react-query";
import { Mail, MessageSquareText } from "lucide-react";

import { listCustomerCommunicationHistory } from "../../api/communications";
import { getApiErrorMessage } from "../../api/errors";
import { Alert, Badge, Card, Spinner } from "../../ui";

type Presentation = {
  label: string;
  detail: string;
  badge: "neutral" | "success" | "warning" | "danger";
};

function deliveryPresentation(item: {
  state: string;
  terminal_failure: boolean;
}): Presentation {
  switch (item.state) {
    case "accepted":
      return {
        label: "Pending delivery",
        detail: "The provider accepted this message. Delivery has not been confirmed.",
        badge: "warning",
      };
    case "delivered":
      return {
        label: "Delivered",
        detail: "The provider reported delivery. This does not mean the Customer read or responded to it.",
        badge: "success",
      };
    case "suppressed":
      return {
        label: "Suppressed",
        detail: "Delivery was not attempted because current contact controls do not allow it.",
        badge: "warning",
      };
    case "uncertain":
      return {
        label: "Needs attention",
        detail: "The submission outcome is uncertain. An authorized operator must reconcile it before any new attempt.",
        badge: "danger",
      };
    case "bounced":
    case "rejected":
    case "failed":
      return {
        label: "Needs attention",
        detail: item.terminal_failure
          ? "Delivery failed and will not retry automatically. An authorized operator should review the contact evidence."
          : "Delivery was not completed. The system will preserve the request while recovery is evaluated.",
        badge: "danger",
      };
    case "deferred":
    case "retry_scheduled":
      return {
        label: "Pending delivery",
        detail: "Delivery is delayed. No Customer action is required.",
        badge: "warning",
      };
    case "canceled":
      return {
        label: "Canceled",
        detail: "This request was canceled. Its delivery history remains unchanged.",
        badge: "neutral",
      };
    default:
      return {
        label: "Pending",
        detail: "The communication request is queued for delivery processing.",
        badge: "neutral",
      };
  }
}

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
      <div aria-live="polite" aria-atomic="false">
        {history.isLoading && <div className="mt-4"><Spinner label="Loading communication history" /></div>}
        {history.isError && <Alert variant="danger" title="Communication history unavailable">{getApiErrorMessage(history.error)}</Alert>}
      </div>
      <div className="mt-5 space-y-3" aria-label="Communication delivery history">
        {(history.data ?? []).map((item) => {
          const presentation = deliveryPresentation(item);
          return <article key={item.id} className="flex min-w-0 gap-3 rounded-xl border border-stroke bg-surface-subtle p-4">
            {item.channel === "email" ? <Mail className="mt-0.5 shrink-0 text-action-primary" size={17} aria-hidden="true" /> : <MessageSquareText className="mt-0.5 shrink-0 text-action-primary" size={17} aria-hidden="true" />}
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">{item.communication_type.replaceAll("_", " ")}</p>
                <Badge variant={presentation.badge}>{presentation.label}</Badge>
              </div>
              <p className="mt-1 break-all text-sm text-content-muted">{item.channel.toUpperCase()} · {item.recipient_display}</p>
              <p className="mt-1 text-xs text-content-muted">Requested {new Date(item.created_at).toLocaleString()}{item.retry_count ? ` · ${item.retry_count} retries` : ""}</p>
              <p className="mt-2 text-xs text-content-muted">{presentation.detail}</p>
            </div>
          </article>;
        })}
      </div>
      {history.isSuccess && history.data.length === 0 && <p className="mt-4 text-sm text-content-muted">No communication requests have been recorded for this Customer.</p>}
    </Card>
  );
}
