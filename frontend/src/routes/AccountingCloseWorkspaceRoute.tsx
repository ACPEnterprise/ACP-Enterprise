import { useState } from "react";
import { Link } from "react-router";

import { previewSealedOpening, sealOpening } from "../api/accountingClose";
import { useHasPermission } from "../auth";
import { CanonicalAccountantClose } from "../components/accounting/CanonicalAccountantClose";
import { OpeningControlProjectionReview } from "../components/accounting/OpeningControlProjectionReview";
import {
  useAccountingPeriods,
  useOpeningControlDetail,
  usePayrollAccountingControl,
} from "../hooks/useAccountingClose";
import { usePayrollOperatingRegisters } from "../hooks/usePayroll";
import { useQboAccountingEvidence } from "../hooks/useQboAccountingEvidence";
import { useQboApplicationLedger } from "../hooks/useQboNativeApplication";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Spinner,
} from "../ui";

export function AccountingCloseWorkspaceRoute() {
  const canRead = useHasPermission("COMPANY_ACCOUNTING_REPORT_READ");
  const canReconcile = useHasPermission("COMPANY_ACCOUNTING_RECONCILE");
  const canManagePeriods = useHasPermission("COMPANY_ACCOUNTING_PERIOD_MANAGE");
  const canApprove = useHasPermission("COMPANY_ACCOUNTING_FINANCE_APPROVE");
  const source = useQboAccountingEvidence("accrual", canRead);
  const periods = useAccountingPeriods(canRead);
  const ledger = useQboApplicationLedger(canRead);
  const [openingPackageId, setOpeningPackageId] = useState<string | null>(null);
  const [previewState, setPreviewState] = useState({
    pending: false,
    error: false,
    ready: false,
  });
  const [sealState, setSealState] = useState({ pending: false, error: false });
  const opening = useOpeningControlDetail(openingPackageId, canRead);
  const payrollRegisters = usePayrollOperatingRegisters(canRead);
  const selectedPayrollRun =
    payrollRegisters.data?.find(
      (item) => item.lifecycle === "approved" || item.lifecycle === "closed",
    ) ??
    payrollRegisters.data?.[0] ??
    null;
  const payrollCutoff = selectedPayrollRun
    ? `${selectedPayrollRun.period_end}T23:59:59Z`
    : null;
  const payrollControl = usePayrollAccountingControl(
    selectedPayrollRun?.run_id ?? null,
    payrollCutoff,
    canRead,
  );

  if (!canRead) {
    return (
      <Alert variant="danger">
        Accounting report permission is required to review close readiness.
      </Alert>
    );
  }
  if (source.isLoading || periods.isLoading) {
    return <Spinner label="Loading accountant close workspace" />;
  }

  const sourceRunId = ledger.data?.source_evidence.source_run_id ?? null;
  const runPreview = async () => {
    if (!sourceRunId) return;
    setPreviewState({ pending: true, error: false, ready: false });
    try {
      await previewSealedOpening(sourceRunId);
      setPreviewState({ pending: false, error: false, ready: true });
    } catch {
      setPreviewState({ pending: false, error: true, ready: false });
    }
  };
  const runSeal = async () => {
    if (!sourceRunId) return;
    setSealState({ pending: true, error: false });
    try {
      const value = await sealOpening(sourceRunId);
      const id =
        typeof value === "object" && value !== null && "id" in value
          ? String(value.id)
          : null;
      if (id) setOpeningPackageId(id);
      setSealState({ pending: false, error: false });
    } catch {
      setSealState({ pending: false, error: true });
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-8 pb-12">
      <header>
        <p className="text-sm font-semibold text-action-primary">Accounting</p>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">
          Accountant close workspace
        </h1>
        <p className="mt-2 text-content-muted">
          Review canonical report comparisons, source-owned exceptions, and
          server-controlled close readiness without changing financial
          authority.
        </p>
      </header>

      <Alert variant="warning" title="Real cutover evidence remains incomplete">
        Software controls are available, but Accounting cutover is not ready
        until real matching QBO and ACP reports, opening controls, Payroll
        evidence, and accountant review are complete.
      </Alert>

      {source.isError ? (
        <Alert variant="warning" title="QuickBooks evidence unavailable">
          Source evidence is unavailable. ACP values are not treated as matching
          QuickBooks.
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Opening package controls</CardTitle>
          <CardDescription>
            Package identity comes from governed QBO custody. The browser
            submits no Trial Balance orientation or control arithmetic.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm">
            Sealed package: {sourceRunId ?? "Unavailable"}
          </p>
          {previewState.error ? (
            <Alert variant="warning">
              The sealed opening preview is unavailable. No client-derived
              opening authority was used.
            </Alert>
          ) : null}
          {previewState.ready ? (
            <Alert variant="information">
              Server preview returned. Review it before persisting the governed
              snapshot.
            </Alert>
          ) : null}
          {sealState.error ? (
            <Alert variant="warning">
              The governed opening snapshot could not be persisted.
            </Alert>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={!sourceRunId || previewState.pending}
              onClick={() => void runPreview()}
            >
              Preview sealed package
            </Button>
            <Button
              variant="secondary"
              disabled={!sourceRunId || sealState.pending}
              onClick={() => void runSeal()}
            >
              Persist governed snapshot
            </Button>
          </div>
          {opening.isError ? (
            <Alert variant="warning">
              Persisted opening-control detail is unavailable.
            </Alert>
          ) : null}
          {opening.data ? (
            <OpeningControlProjectionReview value={opening.data} />
          ) : null}
        </CardContent>
      </Card>

      <CanonicalAccountantClose
        periods={periods.data ?? []}
        canReconcile={canReconcile}
        canManagePeriods={canManagePeriods}
        canApprove={canApprove}
      />

      <Card>
        <CardHeader>
          <CardTitle>Payroll accounting review</CardTitle>
          <CardDescription>
            Payroll authority remains separate from Accounting posting
            authority.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {payrollControl.isError ? (
            <Alert variant="warning">
              Payroll-to-GL evidence is unavailable for the selected run.
              Missing evidence is not displayed as matched or zero.
            </Alert>
          ) : null}
          {payrollControl.data ? (
            <div className="space-y-3">
              <p className="text-sm">
                Run cutoff {payrollControl.data.cutoff_at} · status{" "}
                {payrollControl.data.status} · currency{" "}
                {payrollControl.data.currency}
              </p>
              <div className="overflow-x-auto">
                <table className="min-w-[760px] w-full text-sm">
                  <thead>
                    <tr className="text-left">
                      <th>Category</th>
                      <th>Payroll</th>
                      <th>General Ledger</th>
                      <th>Difference</th>
                      <th>Classification</th>
                      <th>Explanation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {payrollControl.data.findings.map((finding) => (
                      <tr
                        className="border-b border-stroke"
                        key={finding.category}
                      >
                        <td className="py-2">{finding.category}</td>
                        <td>{finding.payroll_amount ?? "Unavailable"}</td>
                        <td>
                          {finding.general_ledger_amount ?? "Unavailable"}
                        </td>
                        <td>{finding.difference ?? "Unavailable"}</td>
                        <td>{finding.disposition}</td>
                        <td>{finding.explanation}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : !payrollControl.isError ? (
            <p className="text-sm text-content-muted">
              No approved or closed Payroll run is available for server-owned
              Payroll-to-GL review.
            </p>
          ) : null}
          <Alert variant="warning">
            This is read-only review. Payroll execution, settlement, and
            Accounting posting remain unavailable from this workspace.
          </Alert>
          <Link
            className="font-semibold text-action-primary underline"
            to="/payroll"
          >
            Open Payroll review
          </Link>
        </CardContent>
      </Card>

      <Alert variant="information" title="Banking remains separate">
        Canonical Cash Flow report comparison does not prove that Banking
        reconciliation is complete. Use Accounting → Banking for bank
        operations.
      </Alert>
    </div>
  );
}
