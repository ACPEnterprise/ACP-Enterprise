import { activeCompanyId, apiClient } from "./client";

export interface CustomerImportBatchResponse {
  batch_id: string;
  status: "staged" | "paused" | "completed" | "failed";
  file_name?: string;
  source_rows: number;
  ready: number;
  duplicates: number;
  held: number;
  rejected: number;
  reused: boolean;
  source_sha256: string;
  mapping_sha256: string;
  file_format: "csv" | "xlsx";
}

export interface CustomerImportAdmissionResponse {
  batch_id: string;
  status: "staged" | "paused" | "completed" | "failed";
  created: number;
  matched: number;
  replayed: number;
  held: number;
  rejected: number;
  processed: number;
}

export async function stageCustomerImport(
  file: File,
  idempotencyKey: string,
  options: {
    provider: string;
    namespace: string;
    mapping: Record<string, string>;
    expectedTenantId?: string;
    signal?: AbortSignal;
  },
): Promise<CustomerImportBatchResponse> {
  const tenantId = activeCompanyId();
  if (!tenantId) throw new Error("Choose an active company before uploading a customer file.");
  if (options.expectedTenantId && options.expectedTenantId !== tenantId) {
    throw new Error("The active company changed. Choose the file again for the current company.");
  }
  const response = await apiClient.post<CustomerImportBatchResponse>(
    "/api/v1/customer-import/batches",
    await file.arrayBuffer(),
    {
      timeout: 300_000,
      headers: {
        "Idempotency-Key": idempotencyKey,
        "X-Customer-Import-Filename": file.name,
        "X-Customer-Import-Provider": options.provider,
        "X-Customer-Import-Namespace": options.namespace,
        "X-Customer-Import-Mapping": JSON.stringify(options.mapping),
        "Content-Type": file.type || (file.name.toLowerCase().endsWith(".xlsx") ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" : "text/csv"),
      },
      signal: options.signal,
    },
  );
  return response.data;
}

export async function admitCustomerImport(
  batchId: string,
  expectedTenantId?: string,
): Promise<CustomerImportAdmissionResponse> {
  const tenantId = activeCompanyId();
  if (!tenantId) throw new Error("Choose an active company before admitting customers.");
  if (expectedTenantId && expectedTenantId !== tenantId) {
    throw new Error("The active company changed. Reopen this import from the original company.");
  }
  const response = await apiClient.post<CustomerImportAdmissionResponse>(
    `/api/v1/customer-import/batches/${encodeURIComponent(batchId)}/admit?limit=500`,
    {},
    {
      timeout: 1_800_000,
      headers: { "Content-Type": "application/json" },
    },
  );
  return response.data;
}
