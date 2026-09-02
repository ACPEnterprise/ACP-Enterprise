import { getOperatorApiError } from "../../api/errors";
import { useDispatchRecommendation } from "../../hooks/useDispatch";
import type { DispatchBoardItem } from "../../types/dispatch";
import { Alert, Card, Spinner } from "../../ui";

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
  const best = result.candidates.find((candidate) => candidate.rank === 1);
  return (
    <Card className="space-y-4 p-ui-4" aria-label="Dispatch recommendation">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-content-muted">
          Proposed placement · no schedule change
        </p>
        <h3 className="mt-1 text-lg font-semibold">Recommended calendar option</h3>
      </div>
      {best ? (
        <div className="rounded-md border border-dashed border-brand p-3">
          <p className="font-medium">Candidate {best.rank}: {label(best.placement_class)}</p>
          <p className="mt-1 text-sm text-content-muted">
            {new Date(best.proposed_window.start_at).toLocaleString()} – {new Date(best.proposed_window.end_at).toLocaleTimeString()}
          </p>
          <h4 className="mt-3 font-medium">Why?</h4>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
            {best.constraints.map((constraint) => (
              <li key={constraint.constraint}>
                {constraint.result}: {constraint.explanation}
              </li>
            ))}
            {best.tradeoffs.map((tradeoff) => <li key={tradeoff}>{tradeoff}</li>)}
          </ul>
        </div>
      ) : (
        <Alert title="No confident placement">
          ACP found no eligible proposal. Review the evidence limitations below.
        </Alert>
      )}
      {result.candidates.filter((candidate) => candidate.rank !== 1).length > 0 && (
        <details>
          <summary className="cursor-pointer font-medium">Alternatives and tradeoffs</summary>
          <ul className="mt-2 space-y-2 text-sm">
            {result.candidates.filter((candidate) => candidate.rank !== 1).slice(0, 5).map((candidate) => (
              <li key={`${candidate.employee_id}-${candidate.proposed_window.start_at}`}>
                {label(candidate.placement_class)} · {candidate.limitations.join(" ") || candidate.tradeoffs.join(" ")}
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
