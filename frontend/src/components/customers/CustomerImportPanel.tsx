import { FileCheck2, FileUp, RefreshCw, ShieldCheck } from "lucide-react";
import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { activeCompanyId } from "../../api/client";
import { useAuth } from "../../auth";
import { getOperatorApiError } from "../../api/errors";
import { admitCustomerImport, stageCustomerImport, type CustomerImportAdmissionResponse, type CustomerImportBatchResponse } from "../../api/customerImports";
import { useCustomerCleanMajorityAdmission, useCustomerPopulationRefresh } from "../../hooks/useCustomers";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Spinner } from "../../ui";
import { type CustomerImportPreview, validateCustomerFile } from "./customerImport";

export function CustomerImportPanel() {
  const { activeCompany } = useAuth();
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<CustomerImportPreview | null>(null);
  const [serverPreview, setServerPreview] = useState<CustomerImportBatchResponse | null>(null);
  const [admitted, setAdmitted] = useState<CustomerImportAdmissionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validating, setValidating] = useState(false);
  const [serverValidationPending, setServerValidationPending] = useState(false);
  const [serverValidationError, setServerValidationError] = useState<unknown>(null);
  const [serverAdmissionPending, setServerAdmissionPending] = useState(false);
  const [serverAdmissionError, setServerAdmissionError] = useState<unknown>(null);
  const [importTenantId, setImportTenantId] = useState<string | null>(null);
  const operationGeneration = useRef(0);
  const validationRequest = useRef<AbortController | null>(null);
  const [sourceProvider, setSourceProvider] = useState<"file" | "housecall_pro">("file");
  const populationRefresh = useCustomerPopulationRefresh();
  const admission = useCustomerCleanMajorityAdmission();
  const tenantId = activeCompanyId() ?? "";
  const branchId = activeCompany?.default_branch_id ?? activeCompany?.branches[0]?.id ?? "";
  const isCurrentOperation = (generation: number, expectedTenantId: string) =>
    operationGeneration.current === generation && activeCompanyId() === expectedTenantId;

  const invalidateImport = () => {
    operationGeneration.current += 1;
    validationRequest.current?.abort();
    validationRequest.current = null;
    setPreview(null);
    setServerPreview(null);
    setAdmitted(null);
    setError(null);
    setServerValidationError(null);
    setServerAdmissionError(null);
    setImportTenantId(null);
    setValidating(false);
    setServerValidationPending(false);
    setServerAdmissionPending(false);
  };

  const validateOnServer = async (
    file: File,
    mapping: Record<string, string>,
    expectedTenantId: string,
    provider: "file" | "housecall_pro",
    generation: number,
    controller: AbortController,
  ) => {
    setServerValidationPending(true);
    setServerValidationError(null);
    try {
      const result = await stageCustomerImport(file, `customer-import-preview-${crypto.randomUUID()}`, {
        provider,
        namespace: provider,
        mapping,
        expectedTenantId,
        branchId,
        signal: controller.signal,
      });
      if (!isCurrentOperation(generation, expectedTenantId)) return;
      setServerPreview(result);
    } catch (reason) {
      if (controller.signal.aborted || !isCurrentOperation(generation, expectedTenantId)) return;
      setServerValidationError(reason);
    } finally {
      if (isCurrentOperation(generation, expectedTenantId)) {
        validationRequest.current = null;
        setServerValidationPending(false);
      }
    }
  };
  const admitOnServer = async () => {
    if (
      !serverPreview
      || !importTenantId
      || serverPreview.ready === 0
      || serverPreview.status === "failed"
      || admitted?.status === "completed"
    ) return;
    const generation = operationGeneration.current;
    const expectedTenantId = importTenantId;
    const batchId = serverPreview.batch_id;
    setServerAdmissionPending(true);
    setServerAdmissionError(null);
    try {
      const result = await admitCustomerImport(batchId, expectedTenantId, branchId);
      if (!isCurrentOperation(generation, expectedTenantId)) return;
      setAdmitted(result);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["customers"] }),
        queryClient.invalidateQueries({ queryKey: ["administration", "migration-readiness"] }),
      ]);
    } catch (reason) {
      if (!isCurrentOperation(generation, expectedTenantId)) return;
      setServerAdmissionError(reason);
    } finally {
      if (isCurrentOperation(generation, expectedTenantId)) setServerAdmissionPending(false);
    }
  };

  const selectFile = async (file: File | undefined) => {
    if (!file || !tenantId) return;
    const generation = operationGeneration.current + 1;
    operationGeneration.current = generation;
    validationRequest.current?.abort();
    const controller = new AbortController();
    validationRequest.current = controller;
    const provider = sourceProvider;
    setPreview(null);
    setServerPreview(null);
    setAdmitted(null);
    setError(null);
    setServerValidationError(null);
    setServerAdmissionError(null);
    setImportTenantId(tenantId);
    setValidating(true);
    try {
      const localPreview = await validateCustomerFile(file, tenantId);
      if (!isCurrentOperation(generation, tenantId)) return;
      setPreview(localPreview);
      void validateOnServer(file, localPreview.sourceMapping, tenantId, provider, generation, controller);
    } catch (reason) {
      if (!isCurrentOperation(generation, tenantId)) return;
      setError(reason instanceof Error ? reason.message : "This file could not be validated.");
      validationRequest.current = null;
    } finally {
      if (isCurrentOperation(generation, tenantId)) setValidating(false);
    }
  };

  const sourceError = populationRefresh.isError ? getOperatorApiError(populationRefresh.error, "connected source import") : null;
  const admissionError = admission.isError ? getOperatorApiError(admission.error, "customer admission") : null;
  const serverError = serverValidationError ? getOperatorApiError(serverValidationError, "file validation service") : null;
  const serverAdmissionFailure = serverAdmissionError ? getOperatorApiError(serverAdmissionError, "customer import") : null;
  const isExcelPreview = preview?.fileKind === "excel";
  const serverCounts = serverPreview;

  return (
    <Card aria-labelledby="customer-import-title" className="primary-work-panel">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2"><FileUp aria-hidden="true" className="text-action-primary" /><CardTitle>Import customers</CardTitle></div>
            <CardDescription>Upload a customer file, check what will happen, and keep duplicates or missing information out of your roster.</CardDescription>
          </div>
          <Badge variant="information">Current company only</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-ui-4">
        <div className="rounded-lg bg-surface-subtle p-ui-3 text-body-s">
          <p><strong>Active company</strong></p>
          <p className="mt-1 text-content-muted">This review is private to the active company. TwelveHats stages the source rows for review; customers are not added to the roster until you admit the qualified rows.</p>
        </div>
        <div className="grid gap-ui-4 lg:grid-cols-2">
          <section className="rounded-lg border border-stroke p-ui-4" aria-labelledby="customer-file-upload-title">
            <h3 id="customer-file-upload-title" className="font-semibold">Upload a CSV or Excel file</h3>
            <p className="mt-1 text-body-s text-content-muted">We need a source customer ID and a customer or company name. The source ID lets us safely retry without making duplicates.</p>
            <label className="mt-ui-3 block text-body-s font-medium">Where did this file come from?<select className="mt-1 min-h-11 w-full rounded-lg border border-stroke-strong bg-surface px-3" value={sourceProvider} onChange={(event) => { invalidateImport(); setSourceProvider(event.target.value as "file" | "housecall_pro"); }}><option value="file">Another system</option><option value="housecall_pro">Housecall Pro</option></select></label>
            {!tenantId && <Alert className="mt-ui-3" variant="warning" title="Choose a company first">Customer imports are always saved to the active company. Select a company before choosing a file.</Alert>}
            <label className="mt-ui-3 block text-body-s font-medium">Choose file<Input key={sourceProvider} disabled={!tenantId} className="mt-1" type="file" accept=".csv,.xlsx,text/csv" onChange={(event) => void selectFile(event.target.files?.[0])} /></label>
            {(validating || serverValidationPending) && <div className="mt-ui-3"><Spinner label={serverValidationPending ? "Sending file for source validation" : "Checking file"} /></div>}
            {error && <Alert className="mt-ui-3" variant="danger" title="File needs attention">{error}</Alert>}
            {preview && <div className="mt-ui-3 space-y-ui-3" aria-live="polite"><div className="flex flex-wrap items-center gap-2"><FileCheck2 size={18} className="text-status-success" /><strong>{preview.fileName}</strong><Badge variant={serverPreview?.status === "failed" ? "danger" : serverPreview ? (serverPreview.held || serverPreview.rejected ? "warning" : "success") : "information"}>{serverPreview?.status === "failed" ? "Validation failed" : serverPreview ? (serverPreview.status === "paused" ? "Staged — more rows remain" : "Staged by TwelveHats") : isExcelPreview ? "Waiting for service validation" : "Browser check only"}</Badge></div><div className="grid gap-2 text-body-s sm:grid-cols-3"><div><span className="text-content-muted">Source rows</span><strong className="block">{serverCounts?.source_rows.toLocaleString() ?? (isExcelPreview ? "Pending" : preview.sourceRows.toLocaleString())}</strong></div><div><span className="text-content-muted">Ready</span><strong className="block">{serverCounts?.ready.toLocaleString() ?? (isExcelPreview ? "Pending" : preview.readyRows.toLocaleString())}</strong></div><div><span className="text-content-muted">Needs review</span><strong className="block">{serverCounts ? (serverCounts.held + serverCounts.rejected).toLocaleString() : (isExcelPreview ? "Pending" : preview.heldRows.toLocaleString())}</strong></div></div><p className="text-body-s text-content-muted">{serverPreview?.status === "failed" ? "TwelveHats could not validate this file. Nothing was admitted." : serverPreview ? "TwelveHats staged this file without admitting any customers." : preview.message}</p>{!serverPreview && preview.heldRows > 0 && <ul className="space-y-1 text-body-s text-status-warning"><li>{preview.missingSourceIds} row(s) missing a source ID</li><li>{preview.missingNames} row(s) missing a name</li><li>{preview.duplicateSourceIds} duplicate source-ID row(s)</li></ul>}{preview.rows.length > 0 && !serverPreview && <div className="overflow-x-auto"><table className="min-w-full text-left text-body-s"><thead><tr><th className="p-2">Row</th><th className="p-2">Customer</th><th className="p-2">Source ID</th><th className="p-2">Status</th></tr></thead><tbody>{preview.rows.map((row) => <tr className="border-t border-stroke" key={`${row.rowNumber}-${row.sourceId}`}><td className="p-2">{row.rowNumber}</td><td className="p-2">{row.displayName || "Name missing"}</td><td className="p-2 font-mono text-xs">{row.sourceId || "Missing"}</td><td className="p-2"><Badge variant={row.status === "ready" ? "success" : "warning"}>{row.status === "ready" ? "Ready" : "Needs review"}</Badge></td></tr>)}</tbody></table></div>}</div>}
            {serverError && <Alert className="mt-ui-3" variant="warning" title="Connected file validation is not available">The browser check is only a preview. Nothing was saved. Connect the customer import service before admitting this file.</Alert>}
            {serverPreview && <div className="mt-ui-3 flex flex-wrap items-center gap-2"><Button type="button" disabled={serverAdmissionPending || serverPreview.ready === 0 || serverPreview.status === "failed" || admitted?.status === "completed"} loading={serverAdmissionPending} onClick={() => void admitOnServer()}>{admitted?.status === "paused" ? "Continue import" : "Admit ready customers"}</Button><span className="text-body-xs text-content-muted">Rows needing review stay held. Completed imports cannot be submitted again.</span></div>}
            {serverAdmissionFailure && <Alert className="mt-ui-3" variant="danger" title="Nothing was admitted">{serverAdmissionFailure.message}</Alert>}
            {admitted && <Alert className="mt-ui-3" variant={admitted.status === "completed" ? "success" : "warning"} title="Import result">{admitted.created.toLocaleString()} added · {admitted.matched.toLocaleString()} matched · {admitted.replayed.toLocaleString()} already present · {admitted.held.toLocaleString()} held for review.</Alert>}
          </section>
          <section className="rounded-lg border border-stroke p-ui-4" aria-labelledby="connected-source-title">
            <div className="flex items-start gap-2"><ShieldCheck aria-hidden="true" className="text-action-primary" /><div><h3 id="connected-source-title" className="font-semibold">Use a connected source</h3><p className="mt-1 text-body-s text-content-muted">For Housecall Pro, TwelveHats uses the existing tenant-scoped source reconciliation contract. It matches exact source identities, keeps ambiguous rows held, and can be safely retried.</p></div></div>
            <div className="mt-ui-4 flex flex-wrap gap-2"><Button type="button" variant="outline" leadingIcon={<RefreshCw size={16} />} loading={populationRefresh.isPending} onClick={() => populationRefresh.mutate()}>Check Housecall Pro</Button><Button type="button" loading={admission.isPending} loadingLabel="Importing safe customers" disabled={admission.isPending} onClick={() => admission.mutate()}>Import safe customers</Button></div>
            {sourceError && <Alert className="mt-ui-3" variant="danger" title={sourceError.title}>{sourceError.message}</Alert>}
            {admissionError && <Alert className="mt-ui-3" variant="danger" title={admissionError.title}>{admissionError.message}</Alert>}
            {populationRefresh.data && <Alert className="mt-ui-3" variant={populationRefresh.data.counts.ambiguous || populationRefresh.data.counts.unexplained ? "warning" : "success"} title="Source check complete">{populationRefresh.data.counts.total.toLocaleString()} source customers checked · {populationRefresh.data.counts.bound.toLocaleString()} already matched · {populationRefresh.data.counts.held.toLocaleString()} held · {populationRefresh.data.counts.ambiguous.toLocaleString()} ambiguous.</Alert>}
            {admission.data && <Alert className="mt-ui-3" variant={admission.data.quarantined || admission.data.remaining_unexplained ? "warning" : "success"} title="Import complete">{admission.data.admitted.toLocaleString()} added · {admission.data.replayed.toLocaleString()} already in TwelveHats · {admission.data.quarantined.toLocaleString()} held for review. No unrelated customer rows were blocked.</Alert>}
          </section>
        </div>
        {preview && !serverPreview && <Alert variant={preview.heldRows ? "warning" : "information"} title="Next step">Review the rows marked Needs review. The browser preview does not merge customers or overwrite native changes. Admission waits for the tenant-scoped import service.</Alert>}
      </CardContent>
    </Card>
  );
}
