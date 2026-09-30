import { getOperatorApiError } from "../../api/errors";
import { useDispatchRecommendation } from "../../hooks/useDispatch";
import type { DispatchBoardItem } from "../../types/dispatch";
import { Alert, Badge, Button, Card, Spinner } from "../../ui";
import { ghostSlotClass } from "./ghostSlots";

const label = (value: string) => value.replaceAll("_", " ").toLowerCase();

export function DispatchRecommendationPanel({
  item,
}: {
  readonly item: DispatchBoardItem;
}) {
  const recommendation = useDispatchRecommendation(
    item.job_id,
    item.window_start_at,
    item.window_end_at,
  );
  if (!item.job_id) return <Alert>Recommendation unavailable: Job authority is missing.</Alert>;
  if (recommendation.isLoading)
    return <Spinner label="Evaluating Dispatch recommendation" />;
  if (recommendation.isError)
    return (
      <Alert variant="danger" title="Recommendation unavailable">
        {getOperatorApiError(recommendation.error, "Dispatch Intelligence").message}
      </Alert>
    );
  const result = recommendation.data;
  if (!result) return null;
  const classified = result.candidates.map((candidate) => ({
    candidate,
    slotClass: ghostSlotClass(candidate),
  }));
  const best = classified.find((item) => item.slotClass === "PRIMARY_GHOST_SLOT");
  return (
    <Card className="space-y-4 p-ui-4" aria-label="Dispatch recommendation">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">
          Proposed placement · no schedule change
        </p>
        <h3 className="mt-1 text-lg font-semibold">Recommended calendar option</h3>
      </div>
      {best ? (
        <div className="rounded-md border-2 border-dashed border-content-muted bg-surface-subtle p-3" data-ghost-slot>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="font-medium">Candidate {best.candidate.rank}: {label(best.candidate.placement_class)}</p>
            <Badge>Ghost recommendation</Badge>
          </div>
          <p className="mt-1 text-sm text-content-muted">
            {new Date(best.candidate.proposed_window.start_at).toLocaleString()} – {new Date(best.candidate.proposed_window.end_at).toLocaleTimeString()}
          </p>
          <h4 className="mt-3 font-medium">Why?</h4>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
            {best.candidate.constraints.map((constraint) => (
              <li key={constraint.constraint}>
                {constraint.result}: {constraint.explanation}
              </li>
            ))}
            {best.candidate.tradeoffs.map((tradeoff) => <li key={tradeoff}>{tradeoff}</li>)}
          </ul>
          <Button
            className="mt-3"
            variant="outline"
            onClick={() =>
              document
                .querySelector<HTMLElement>(`[aria-label="Assignment for ${item.appointment_number}"]`)
                ?.scrollIntoView({ behavior: "smooth", block: "start" })
            }
          >
            Review in assignment controls
          </Button>
          <p className="mt-2 text-xs text-content-muted">No Appointment or capacity reservation exists for this visual suggestion.</p>
        </div>
      ) : (
        <Alert title="No confident placement">
          ACP found no eligible proposal. Review the evidence limitations below.
        </Alert>
      )}
      {classified.filter((item) => item.slotClass !== "PRIMARY_GHOST_SLOT").length > 0 && (
        <details>
          <summary className="cursor-pointer font-medium">Alternatives and tradeoffs</summary>
          <ul className="mt-2 space-y-2 text-sm">
            {classified.filter((item) => item.slotClass !== "PRIMARY_GHOST_SLOT").slice(0, 5).map(({ candidate, slotClass }) => (
              <li key={`${candidate.employee_id}-${candidate.proposed_window.start_at}`}>
                <strong>{label(slotClass)}</strong> · {label(candidate.placement_class)} · {candidate.limitations.join(" ") || candidate.tradeoffs.join(" ")}
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="text-xs text-content-muted">
        Dispatcher approval is required. Accepting an option must use the existing Scheduling or Dispatch command.
      </p>
    </Card>
  );
}
