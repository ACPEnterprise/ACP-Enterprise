import { useState, type FormEvent } from "react";
import type {
  BranchPurchasingPolicy,
  BranchPurchasingPolicyWrite,
} from "../../types/purchasing";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Select,
} from "../../ui";

interface Props {
  policies: readonly BranchPurchasingPolicy[];
  canManage: boolean;
  pending: boolean;
  error: boolean;
  onSave: (input: BranchPurchasingPolicyWrite) => Promise<unknown>;
}

export function BranchPurchasingPolicyWorkbench({
  policies,
  canManage,
  pending,
  error,
  onSave,
}: Props) {
  const [branchId, setBranchId] = useState("");
  const [itemId, setItemId] = useState("");
  const [target, setTarget] = useState("0");
  const [provenance, setProvenance] = useState("");
  const [reason, setReason] = useState("");
  const [status, setStatus] = useState<"active" | "inactive">("active");
  const existing = policies.find(
    (policy) => policy.branch_id === branchId && policy.inventory_item_id === itemId,
  );
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void onSave({
      branch_id: branchId.trim(),
      inventory_item_id: itemId.trim(),
      target_available_quantity: target,
      status,
      provenance_reference: provenance.trim(),
      reason: reason.trim(),
      expected_version: existing?.version ?? null,
      idempotency_key: crypto.randomUUID(),
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Branch replenishment policies</CardTitle>
        <CardDescription>
          Explicit branch/item targets with versioned provenance. Vendor, price,
          receiving, AP, and Accounting authority remain separate.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error && (
          <Alert variant="danger">
            Policy configuration failed. No target change was assumed effective.
          </Alert>
        )}
        <ul className="space-y-2">
          {policies.map((policy) => (
            <li key={policy.id} className="rounded border border-stroke p-3 text-sm">
              <strong>{policy.inventory_item_id}</strong> · branch {policy.branch_id}{" "}
              <Badge>{policy.status}</Badge>
              <div>
                Target {policy.target_available_quantity} · version {policy.version}
              </div>
              <div className="text-content-muted">{policy.provenance_reference}</div>
            </li>
          ))}
        </ul>
        {!canManage ? (
          <p className="mt-3 text-sm text-content-muted">
            Read-only policy evidence. Purchasing management permission is required
            to configure a target.
          </p>
        ) : (
          <form className="mt-4 grid gap-3 sm:grid-cols-3" onSubmit={submit}>
            <Input required aria-label="Policy branch ID" value={branchId} onChange={(event) => setBranchId(event.target.value)} placeholder="Branch ID" />
            <Input required aria-label="Policy inventory item ID" value={itemId} onChange={(event) => setItemId(event.target.value)} placeholder="Inventory item ID" />
            <Input required aria-label="Policy target quantity" type="number" min="0" step="0.000001" value={target} onChange={(event) => setTarget(event.target.value)} />
            <Select aria-label="Policy status" value={status} onChange={(event) => setStatus(event.target.value as "active" | "inactive")}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </Select>
            <Input required aria-label="Policy provenance" value={provenance} onChange={(event) => setProvenance(event.target.value)} placeholder="Approved evidence reference" />
            <Input required aria-label="Policy reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Reason for configuration" />
            <Button type="submit" loading={pending}>Save branch policy</Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
