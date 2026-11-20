export type CustomerImportFileKind = "csv" | "excel";

export type CustomerImportRow = {
  rowNumber: number;
  sourceId: string;
  displayName: string;
  email: string;
  phone: string;
  address: string;
  status: "ready" | "held";
  reasons: string[];
};

export type CustomerImportPreview = {
  fileName: string;
  fileKind: CustomerImportFileKind;
  tenantId: string;
  headers: string[];
  sourceRows: number;
  readyRows: number;
  heldRows: number;
  duplicateSourceIds: number;
  missingSourceIds: number;
  missingNames: number;
  sourceMapping: Record<string, string>;
  rows: CustomerImportRow[];
  message: string;
};

const MAX_FILE_BYTES = 25 * 1024 * 1024;

const aliases: Record<string, string> = {
  "customer id": "customer_id",
  "customer number": "customer_id",
  "source customer id": "customer_id",
  "source id": "customer_id",
  id: "customer_id",
  "display name": "display_name",
  "customer name": "display_name",
  name: "display_name",
  "first name": "first_name",
  "last name": "last_name",
  company: "company",
  "company name": "company",
  email: "email",
  emails: "emails",
  phone: "phone",
  "mobile number": "phone",
  "mobile phone": "phone",
  "home number": "phone",
  "service address": "service_address",
  address: "service_address",
  city: "service_city",
  state: "service_state",
  "postal code": "service_postal_code",
  zip: "service_postal_code",
};

function normalizeHeader(value: string): string {
  const normalized = value.trim().toLowerCase().replace(/[/_-]+/g, " ").replace(/\s+/g, " ");
  return aliases[normalized] ?? normalized.replaceAll(" ", "_");
}

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    const next = text[index + 1];
    if (character === '"' && quoted && next === '"') {
      value += '"';
      index += 1;
    } else if (character === '"') {
      quoted = !quoted;
    } else if (character === "," && !quoted) {
      row.push(value);
      value = "";
    } else if ((character === "\n" || character === "\r") && !quoted) {
      if (character === "\r" && next === "\n") index += 1;
      row.push(value);
      if (row.some((cell) => cell.trim())) rows.push(row);
      row = [];
      value = "";
    } else {
      value += character;
    }
  }
  row.push(value);
  if (row.some((cell) => cell.trim())) rows.push(row);
  return rows;
}

function value(record: Record<string, string>, ...keys: string[]): string {
  for (const key of keys) {
    const candidate = record[key]?.trim();
    if (candidate) return candidate;
  }
  return "";
}

export function fileKind(fileName: string): CustomerImportFileKind | null {
  const lower = fileName.toLowerCase();
  if (lower.endsWith(".csv")) return "csv";
  if (lower.endsWith(".xlsx")) return "excel";
  return null;
}

export function validateCustomerCsv(
  text: string,
  fileName: string,
  tenantId: string,
): CustomerImportPreview {
  const rows = parseCsv(text);
  const rawHeaders = rows.shift() ?? [];
  const headers = rawHeaders.map(normalizeHeader);
  const sourceMapping: Record<string, string> = {};
  headers.forEach((header, index) => {
    if (header && header !== "source_record_id" && ["display_name", "first_name", "last_name", "company", "email", "emails", "phone", "service_address", "service_city", "service_state", "service_postal_code"].includes(header)) {
      const canonical = header === "company" ? "company_name" : header === "emails" ? "email" : header === "phone" ? "phone" : header.startsWith("service_") ? header.replace("service_", "") : header;
      sourceMapping[canonical] ??= rawHeaders[index] ?? header;
    }
    if (header === "customer_id") sourceMapping.source_record_id = rawHeaders[index] ?? header;
  });
  const sourceIdCounts = new Map<string, number>();
  rows.forEach((cells) => {
    const record = Object.fromEntries(headers.map((header, cellIndex) => [header, cells[cellIndex] ?? ""]));
    const sourceId = value(record, "customer_id");
    if (sourceId) sourceIdCounts.set(sourceId, (sourceIdCounts.get(sourceId) ?? 0) + 1);
  });
  const stagedRows: CustomerImportRow[] = [];

  rows.forEach((cells, index) => {
    const record = Object.fromEntries(headers.map((header, cellIndex) => [header, cells[cellIndex] ?? ""]));
    const sourceId = value(record, "customer_id");
    const displayName = value(record, "display_name", "company") || [
      value(record, "first_name"),
      value(record, "last_name"),
    ].filter(Boolean).join(" ");
    const reasons: string[] = [];
    if (!sourceId) reasons.push("Add a source customer ID so retries cannot create duplicates.");
    if (!displayName) reasons.push("Add a customer or company name.");
    if (sourceId && (sourceIdCounts.get(sourceId) ?? 0) > 1) reasons.push("This source customer ID appears more than once in the file.");
    stagedRows.push({
      rowNumber: index + 2,
      sourceId,
      displayName,
      email: value(record, "email", "emails"),
      phone: value(record, "phone"),
      address: value(record, "service_address", "service_city", "service_state", "service_postal_code"),
      status: reasons.length ? "held" : "ready",
      reasons,
    });
  });

  const duplicateSourceIds = stagedRows.filter((row) => row.reasons.some((reason) => reason.includes("appears more than once"))).length;
  const missingSourceIds = stagedRows.filter((row) => !row.sourceId).length;
  const missingNames = stagedRows.filter((row) => !row.displayName).length;
  const heldRows = stagedRows.filter((row) => row.status === "held").length;
  return {
    fileName,
    fileKind: "csv",
    tenantId,
    headers,
    sourceRows: stagedRows.length,
    readyRows: stagedRows.length - heldRows,
    heldRows,
    duplicateSourceIds,
    missingSourceIds,
    missingNames,
    sourceMapping,
    rows: stagedRows.slice(0, 8),
    message: heldRows
      ? "The file is readable, but held rows need review before they can be admitted."
      : "Every row has the minimum identity fields needed for a safe, repeatable import preview.",
  };
}

export function validateCustomerFile(file: File, tenantId: string): Promise<CustomerImportPreview> {
  const kind = fileKind(file.name);
  if (!kind) return Promise.reject(new Error("Choose a CSV or Excel file."));
  if (file.size > MAX_FILE_BYTES) return Promise.reject(new Error("This file is larger than 25 MB. Split it into smaller files and try again."));
  if (kind === "excel") {
    return Promise.resolve({
      fileName: file.name,
      fileKind: kind,
      tenantId,
      headers: [],
      sourceRows: 0,
      readyRows: 0,
      heldRows: 0,
      duplicateSourceIds: 0,
      missingSourceIds: 0,
      missingNames: 0,
      sourceMapping: { source_record_id: "customer_id", display_name: "display_name", first_name: "first_name", last_name: "last_name", company_name: "company_name", email: "email", phone: "phone", address: "address", city: "city", state: "state", postal_code: "postal_code" },
      rows: [],
      message: "Excel file received. The connected import service will validate its sheets and fields before anything is saved.",
    });
  }
  return file.text().then((text) => validateCustomerCsv(text, file.name, tenantId));
}
