import { Clock3, MapPin } from "lucide-react";
import { Link } from "react-router";

import type { TechnicianItineraryItem } from "../../types/technician";
import { Badge, Card, CardContent, CardHeader, CardTitle } from "../../ui";
import { TechnicianFieldPanel } from "./TechnicianFieldPanel";

const time = new Intl.DateTimeFormat(undefined, {
  hour: "numeric",
  minute: "2-digit",
});

function statusLabel(item: TechnicianItineraryItem) {
  if (item.assignment_status === "reconciliation_required") {
    return "Needs dispatch review";
  }
  if (item.arrival_state === "arrived") return "Arrived";
  if (item.arrival_state === "en_route") return "En route";
  return item.assignment_status === "acknowledged" ? "Acknowledged" : "Assigned";
}

export function TechnicianItineraryCard({ item }: { readonly item: TechnicianItineraryItem }) {
  const warning = item.assignment_status === "reconciliation_required";
  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row items-start justify-between gap-ui-3">
        <div className="min-w-0">
          <p className="text-caption font-semibold text-content-muted">
            {item.appointment_number}
          </p>
          <CardTitle className="mt-ui-1 truncate">{item.customer_display_name}</CardTitle>
        </div>
        <Badge variant={warning ? "warning" : "information"}>{statusLabel(item)}</Badge>
      </CardHeader>
      <CardContent className="space-y-ui-3">
        <p className="flex gap-ui-2 text-body-s text-content-secondary">
          <Clock3 aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span>
            {time.format(new Date(item.window_start_at))}–{time.format(new Date(item.window_end_at))}
          </span>
        </p>
        <p className="flex gap-ui-2 text-body-s text-content-secondary">
          <MapPin aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span>{item.service_location_label}</span>
        </p>
        {item.job_id ? (
          <Link
            className="inline-flex min-h-11 items-center font-semibold text-action-primary underline-offset-4 hover:underline"
            to={`/jobs/${item.job_id}`}
          >
            Open {item.job_number ?? "job"}
          </Link>
        ) : (
          <p className="text-body-s text-content-muted">Job details are not available yet.</p>
        )}
        {item.job_id && item.field_execution_enabled && <TechnicianFieldPanel item={item} />}
      </CardContent>
    </Card>
  );
}
