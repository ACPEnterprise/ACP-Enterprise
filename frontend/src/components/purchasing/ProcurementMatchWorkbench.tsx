import { useState, type FormEvent } from "react";
import axios from "axios";
import {
  useProcurementMatch,
  useProcurementMatchMutations,
} from "../../hooks/useProcurementMatching";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
} from "../../ui";

type Props = { canReview: boolean };

const safeError = (error: unknown) => {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 409)
      return "Matching evidence changed or conflicts with existing authority. Refresh before continuing.";
    if (error.response?.status === 403)
      return "You are not authorized to review this match.";
    if (error.response?.status === 422)
      return "The matching evidence is incomplete or invalid.";
  }
  return error
    ? "The match operation failed safely. No source evidence was changed."
    : null;
};

export function ProcurementMatchWorkbench({ canReview }: Props) {
  const [matchId, setMatchId] = useState("");
  const [form, setForm] = useState({
    purchase_order_id: "",
    vendor_bill_id: "",
    po_version: "1",
    bill_version: "1",
  });
  const [resolutionNote, setResolutionNote] = useState<Record<string, string>>(
    {},
  );
  const query = useProcurementMatch(matchId);
  const mutations = useProcurementMatchMutations();
  const match = query.data ?? mutations.evaluate.data ?? mutations.resolve.data;
  const error = safeError(
    mutations.evaluate.error ?? mutations.resolve.error ?? query.error,
  );
  const busy = mutations.evaluate.isPending || mutations.resolve.isPending;
  const evaluate = async (event: FormEvent) => {
    event.preventDefault();
    const result = await mutations.evaluate.mutateAsync({
      purchase_order_id: form.purchase_order_id,
      vendor_bill_id: form.vendor_bill_id,
      expected_purchase_order_version: Number(form.po_version),
      expected_bill_version: Number(form.bill_version),
      idempotency_key: crypto.randomUUID(),
    });
    setMatchId(result.id);
  };
  return (
    <Card>
      <CardHeader>
        <CardTitle>PO · receipt · Vendor Bill match</CardTitle>
        <CardDescription>
          Evidence is compared without rewriting the PO, receipt, or bill.
          Variances require explicit independent review.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {canReview ? (
          <form
            className="grid gap-3 md:grid-cols-2"
            onSubmit={(event) => void evaluate(event)}
          >
            <Input
              aria-label="Purchase Order identity"
              required
              placeholder="Purchase Order UUID"
              value={form.purchase_order_id}
              onChange={(event) =>
                setForm({ ...form, purchase_order_id: event.target.value })
              }
            />
            <Input
              aria-label="Vendor Bill identity"
              required
              placeholder="Vendor Bill UUID"
              value={form.vendor_bill_id}
              onChange={(event) =>
                setForm({ ...form, vendor_bill_id: event.target.value })
              }
            />
            <Input
              aria-label="Purchase Order version"
              required
              min="1"
              type="number"
              value={form.po_version}
              onChange={(event) =>
                setForm({ ...form, po_version: event.target.value })
              }
            />
            <Input
              aria-label="Vendor Bill version"
              required
              min="1"
              type="number"
              value={form.bill_version}
              onChange={(event) =>
                setForm({ ...form, bill_version: event.target.value })
              }
            />
            <Button
              disabled={busy}
              loading={mutations.evaluate.isPending}
              type="submit"
            >
              Evaluate match
            </Button>
          </form>
        ) : (
          <Alert>
            Read-only access: matching and exception disposition controls
            require AP match-review authority.
          </Alert>
        )}
        <div className="flex gap-2">
          <Input
            aria-label="Match identity"
            placeholder="Existing match UUID"
            value={matchId}
            onChange={(event) => setMatchId(event.target.value)}
          />
        </div>
        {error && <Alert variant="danger">{error}</Alert>}
        {match && (
          <div className="space-y-3" aria-live="polite">
            <p className="font-semibold">
              {match.state.replaceAll("_", " ")} · AP admission{" "}
              {match.admission_state.replaceAll("_", " ")}
            </p>
            <p className="text-sm text-content-muted">
              Evaluation {match.evaluation_sequence} · evaluated{" "}
              {new Date(match.evaluated_at).toLocaleString()} · evidence{" "}
              {match.evidence_digest.slice(0, 12)}…
            </p>
            {match.superseded_at && (
              <Alert variant="danger">
                This evaluation was superseded by newer receipt, return, Vendor
                credit, PO, or bill evidence. It cannot authorize AP admission
                or exception disposition.
              </Alert>
            )}
            {match.lines.map((line) => (
              <div
                className="rounded-lg border border-stroke p-3 text-sm"
                key={line.id}
              >
                <p className="font-medium">
                  Line {line.state.replaceAll("_", " ")}
                </p>
                <p>
                  Ordered {line.ordered_quantity} · received{" "}
                  {line.received_quantity} · returned {line.returned_quantity} ·
                  net accepted {line.net_accepted_quantity} · billed{" "}
                  {line.billed_quantity}
                </p>
                <p>
                  PO unit cost {line.po_unit_cost} · billed unit cost{" "}
                  {line.billed_unit_cost}
                </p>
              </div>
            ))}
            {match.exceptions.map((item) => (
              <div
                className="rounded-lg border border-stroke p-3 text-sm"
                key={item.id}
              >
                <p className="font-medium">
                  {item.category.replaceAll("_", " ")} · {item.status}
                </p>
                <p>Expected: {item.expected_evidence}</p>
                <p>Actual: {item.actual_evidence}</p>
                {canReview &&
                  !match.superseded_at &&
                  item.status !== "resolved" && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Input
                        aria-label={`Resolution note ${item.id}`}
                        placeholder="Independent review evidence"
                        value={resolutionNote[item.id] ?? ""}
                        onChange={(event) =>
                          setResolutionNote({
                            ...resolutionNote,
                            [item.id]: event.target.value,
                          })
                        }
                      />
                      <Button
                        disabled={busy || !resolutionNote[item.id]?.trim()}
                        onClick={() =>
                          void mutations.resolve.mutateAsync({
                            matchId: match.id,
                            exceptionId: item.id,
                            expected_match_version: match.version,
                            expected_exception_version: item.version,
                            resolution: "accept_variance",
                            note: resolutionNote[item.id],
                            idempotency_key: crypto.randomUUID(),
                          })
                        }
                      >
                        Accept variance
                      </Button>
                      <Button
                        variant="secondary"
                        disabled={busy || !resolutionNote[item.id]?.trim()}
                        onClick={() =>
                          void mutations.resolve.mutateAsync({
                            matchId: match.id,
                            exceptionId: item.id,
                            expected_match_version: match.version,
                            expected_exception_version: item.version,
                            resolution: "hold_bill",
                            note: resolutionNote[item.id],
                            idempotency_key: crypto.randomUUID(),
                          })
                        }
                      >
                        Hold bill
                      </Button>
                    </div>
                  )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
