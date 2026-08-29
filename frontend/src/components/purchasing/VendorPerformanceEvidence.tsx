import { useState } from "react";
import { useVendorPerformance } from "../../hooks/useProcurementMatching";
import { Alert, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Spinner } from "../../ui";

const initialAsOf = () => new Date().toISOString().slice(0, 16);

export function VendorPerformanceEvidence() {
  const [asOf, setAsOf] = useState(initialAsOf);
  const report = useVendorPerformance(asOf ? new Date(asOf).toISOString() : "", undefined, Boolean(asOf));
  return <Card><CardHeader><CardTitle>Vendor operational evidence</CardTitle><CardDescription>Deterministic Purchasing outcomes only. No score, financial impact, or autonomous Vendor selection is inferred.</CardDescription></CardHeader><CardContent className="space-y-3">
    <label className="block text-sm">Evidence cutoff <Input aria-label="Vendor performance cutoff" type="datetime-local" value={asOf} onChange={(event) => setAsOf(event.target.value)}/></label>
    {report.isPending ? <Spinner label="Loading Vendor evidence" /> : report.isError ? <Alert variant="danger">Vendor evidence could not be reconciled. Missing evidence is not reported as zero.</Alert> : report.data?.items.length ? <div className="space-y-2">{report.data.items.map((item) => <div className="rounded-lg border border-stroke p-3 text-sm" key={item.vendor_id}><p className="font-medium">Vendor {item.vendor_id}</p><p>{item.purchase_order_count} POs · ordered {item.ordered_quantity} · accepted {item.accepted_received_quantity} · returned {item.returned_quantity} · net {item.net_accepted_quantity}</p><p>Fulfillment evidence {item.fulfillment_ratio ?? "insufficient"} · average lead time {item.average_lead_time_days ?? "insufficient"} days ({item.completed_lead_time_samples} samples)</p><p>{item.discrepancy_count} discrepancies · {item.price_variance_line_count} price-variance lines</p></div>)}</div> : <p className="text-content-muted">No issued Purchasing evidence exists for this cutoff and authorized Branch scope.</p>}
  </CardContent></Card>;
}
