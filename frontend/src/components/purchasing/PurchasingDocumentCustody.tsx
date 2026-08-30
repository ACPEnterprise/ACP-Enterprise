import { useState, type FormEvent } from "react";
import type { PurchasingDocument } from "../../types/purchasing";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Select } from "../../ui";

interface Props {
  canManage: boolean;
  documents: readonly PurchasingDocument[];
  register: (input: {
    branch_id: string; entity_type: "purchase_order" | "requisition" | "receipt" | "discrepancy" | "purchase_return";
    entity_id: string; document_type: string; filename: string; media_type: string;
    content_digest: string; storage_reference: string; source_reference: string; idempotency_key: string;
  }) => Promise<unknown>;
  pending: boolean;
  failed: boolean;
}

export function PurchasingDocumentCustody({ canManage, documents, register, pending, failed }: Props) {
  const [form, setForm] = useState({ branch_id: "", entity_type: "purchase_order" as const, entity_id: "", document_type: "purchase_order", filename: "", media_type: "application/pdf", content_digest: "", storage_reference: "", source_reference: "" });
  const [submissionFailed, setSubmissionFailed] = useState(false);
  const submitCurrent = async () => {
    setSubmissionFailed(false);
    try {
      await register({ ...form, idempotency_key: crypto.randomUUID() });
      setForm({ ...form, filename: "", content_digest: "", storage_reference: "", source_reference: "" });
    } catch {
      setSubmissionFailed(true);
    }
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await submitCurrent();
  };
  return <Card>
    <CardHeader><CardTitle>Purchasing document custody</CardTitle><CardDescription>Append-only metadata binds approved documents to Purchasing evidence. Files remain in the authorized document provider; no Vendor transmission occurs here.</CardDescription></CardHeader>
    <CardContent className="space-y-4">
      {!canManage && <Alert>Read-only access: document evidence is visible, but registration controls require Purchasing management authority.</Alert>}
      {(failed || submissionFailed) && <Alert variant="danger" announcement="assertive" action={<Button type="button" onClick={() => void submitCurrent()} loading={pending}>Retry registration</Button>}>Document evidence was not registered. No custody authority was assumed. Review the retained evidence and retry.</Alert>}
      {canManage && <form className="grid gap-2 md:grid-cols-3" onSubmit={(event) => void submit(event)}>
        <Input aria-label="Document branch ID" required value={form.branch_id} onChange={(event) => setForm({ ...form, branch_id: event.target.value })} />
        <Select aria-label="Document entity type" value={form.entity_type} onChange={(event) => setForm({ ...form, entity_type: event.target.value as typeof form.entity_type })}><option value="purchase_order">Purchase Order</option><option value="requisition">Requisition</option><option value="receipt">Receipt</option><option value="discrepancy">Discrepancy</option><option value="purchase_return">Purchase return</option></Select>
        <Input aria-label="Document entity ID" required value={form.entity_id} onChange={(event) => setForm({ ...form, entity_id: event.target.value })} />
        <Input aria-label="Document filename" required value={form.filename} onChange={(event) => setForm({ ...form, filename: event.target.value })} />
        <Input aria-label="Document media type" required value={form.media_type} onChange={(event) => setForm({ ...form, media_type: event.target.value })} />
        <Input aria-label="Document SHA-256" required pattern="[0-9a-f]{64}" value={form.content_digest} onChange={(event) => setForm({ ...form, content_digest: event.target.value })} />
        <Input aria-label="Authorized storage reference" required value={form.storage_reference} onChange={(event) => setForm({ ...form, storage_reference: event.target.value })} />
        <Input aria-label="Source reference" required value={form.source_reference} onChange={(event) => setForm({ ...form, source_reference: event.target.value })} />
        <Button type="submit" loading={pending}>Register evidence</Button>
      </form>}
      <ul className="space-y-2">{documents.map((document) => <li className="rounded border border-stroke p-3 text-sm" key={document.id}><strong>{document.filename}</strong> <Badge>{document.document_type}</Badge><div className="text-content-muted">{document.entity_type} · {document.entity_id} · SHA-256 {document.content_digest.slice(0, 12)}…</div></li>)}</ul>
    </CardContent>
  </Card>;
}
