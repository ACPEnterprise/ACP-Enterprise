import { useParams } from "react-router";
import { useHasPermission } from "../auth";
import { InvoiceSummary } from "../components/invoices/InvoiceSummary";
import { useInvoice, useInvoiceMutations } from "../hooks/useInvoices";
import { Alert, Button, Spinner } from "../ui";

export function InvoiceDetailRoute() {
  const { invoiceId = "" } = useParams();
  const invoice = useInvoice(invoiceId);
  const canIssue = useHasPermission("COMPANY_INVOICE_ISSUE");
  const mutations = useInvoiceMutations();
  if (invoice.isPending) return <Spinner label="Loading Invoice" />;
  if (invoice.isError || !invoice.data)
    return <Alert variant="danger">Invoice could not be loaded.</Alert>;
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <InvoiceSummary invoice={invoice.data} />
      {invoice.data.status === "draft" && canIssue && (
        <Button
          loading={mutations.issue.isPending}
          onClick={() =>
            void mutations.issue.mutateAsync({
              id: invoice.data.id,
              input: {
                branch_id: invoice.data.branch_id,
                expected_version: invoice.data.version,
                idempotency_key: crypto.randomUUID(),
                occurred_at: new Date().toISOString(),
              },
            })
          }
        >
          Issue Invoice
        </Button>
      )}
    </div>
  );
}
