import { ArrowRight, Banknote, CreditCard, FileText, ReceiptText, Scale } from "lucide-react";
import { Link } from "react-router";

import { useEffectivePermissions } from "../auth/usePermissions";
import { Alert, Card } from "../ui";

const destinations = [
  {
    label: "Financial Reports",
    description: "Trial Balance, Balance Sheet, Income Statement, General Ledger, and QBO source evidence.",
    path: "/financial-reports",
    permissions: ["COMPANY_ACCOUNTING_REPORT_READ"],
    icon: Scale,
  },
  {
    label: "Accounts Receivable",
    description: "Existing Invoice lifecycle, balances, and accounting-control evidence.",
    path: "/invoices",
    permissions: ["COMPANY_INVOICE_READ"],
    icon: FileText,
  },
  {
    label: "Accounts Payable",
    description: "Vendor liabilities, credits, aging, and verified disbursement evidence.",
    path: "/accounts-payable",
    permissions: ["COMPANY_ACCOUNTS_PAYABLE_READ", "COMPANY_ACCOUNTS_PAYABLE_REPORT_READ"],
    icon: ReceiptText,
  },
  {
    label: "Payments & Receipts",
    description: "Provider-neutral payment receipt and settlement evidence.",
    path: "/payments",
    permissions: ["COMPANY_PAYMENT_READ"],
    icon: CreditCard,
  },
  {
    label: "Payroll Accounting",
    description: "Existing Payroll reporting, readiness, and accounting context.",
    path: "/payroll",
    permissions: ["COMPANY_PAYROLL_REPORTING_READ"],
    icon: Banknote,
  },
] as const;

export function AccountingRoute() {
  const permissions = useEffectivePermissions();
  const visibleDestinations = destinations.filter((destination) =>
    destination.permissions.some((permission) => permissions.has(permission)),
  );

  return (
    <div className="mx-auto max-w-6xl space-y-6 pb-12">
      <header>
        <p className="text-sm font-semibold text-action-primary">Accounting</p>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">Accounting workspace</h1>
        <p className="mt-2 max-w-3xl text-content-muted">
          Open existing accounting and reconciliation surfaces. This workspace does not create a second ledger or infer financial results.
        </p>
      </header>

      {visibleDestinations.length === 0 ? (
        <Alert variant="danger">You do not have permission to open an Accounting workspace.</Alert>
      ) : (
        <nav aria-label="Accounting tasks" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {visibleDestinations.map((destination) => (
            <Card key={destination.path} className="p-5">
              <destination.icon aria-hidden="true" className="size-5 text-action-primary" />
              <h2 className="mt-3 text-lg font-semibold">{destination.label}</h2>
              <p className="mt-2 text-sm text-content-muted">{destination.description}</p>
              <Link
                className="mt-4 inline-flex min-h-11 items-center gap-2 font-semibold text-action-primary hover:underline"
                to={destination.path}
              >
                Open {destination.label}
                <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
            </Card>
          ))}
        </nav>
      )}
    </div>
  );
}
