import { Lightbulb } from "lucide-react";
import { Link } from "react-router";

import type { ActiveBeaconRecommendation } from "../../api/beacon";
import { Alert, Badge, Card, CardContent, CardHeader, CardTitle, Spinner } from "../../ui";

const windows = ["NOW", "TODAY", "THIS_WEEK", "WATCH"] as const;

const labels = {
  NOW: "Now",
  TODAY: "Today",
  THIS_WEEK: "This week",
  WATCH: "Watch",
} as const;

export function BeaconReasoningPanel({
  items,
  isPending,
  isError,
  evaluatedAt,
}: {
  readonly items: readonly ActiveBeaconRecommendation[] | undefined;
  readonly isPending: boolean;
  readonly isError: boolean;
  readonly evaluatedAt?: string;
}) {
  return (
    <Card className="bg-surface">
      <CardHeader>
        <div className="flex items-center gap-2 text-action-primary">
          <Lightbulb aria-hidden="true" size={20} />
          <CardTitle>Beacon reasoning</CardTitle>
        </div>
        <p className="text-sm text-content-muted">
          Evidence-backed management attention. Beacon recommends human review;
          it does not change operations.
        </p>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <Spinner label="Evaluating management evidence" />
        ) : isError ? (
          <Alert variant="warning">
            Beacon could not evaluate its canonical evidence. No recommendation
            state is inferred.
          </Alert>
        ) : !items?.length ? (
          <Alert variant="information">
            No additional evidence-backed recommendations are active. This does
            not mean every source is complete.
          </Alert>
        ) : (
          <div className="space-y-6">
            {windows.map((window) => {
              const group = items.filter(
                (recommendation) => recommendation.priority_window === window,
              );
              if (!group.length) return null;
              return (
                <section key={window} aria-labelledby={`beacon-reasoning-${window}`}>
                  <h3
                    className="mb-3 text-lg font-semibold text-content"
                    id={`beacon-reasoning-${window}`}
                  >
                    {labels[window]}
                  </h3>
                  <ol className="grid gap-4 xl:grid-cols-2">
                    {group.map((recommendation) => (
                      <li
                        className="rounded-lg border border-stroke bg-surface-muted p-4"
                        key={recommendation.recommendation_id}
                      >
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <h4 className="font-semibold text-content">
                            {recommendation.title}
                          </h4>
                          <Badge
                            variant={
                              recommendation.kind === "EVIDENCE_GAP"
                                ? "warning"
                                : "neutral"
                            }
                          >
                            {recommendation.kind === "EVIDENCE_GAP"
                              ? "Evidence gap"
                              : "Measured finding"}
                          </Badge>
                        </div>
                        <dl className="mt-4 space-y-3 text-sm">
                          <div>
                            <dt className="font-semibold text-content">Measured fact</dt>
                            <dd className="text-content-muted">
                              {recommendation.measured_fact}
                            </dd>
                          </div>
                          <div>
                            <dt className="font-semibold text-content">Interpretation</dt>
                            <dd className="text-content-muted">
                              {recommendation.interpretation}
                            </dd>
                          </div>
                          <div>
                            <dt className="font-semibold text-content">
                              Recommended human action
                            </dt>
                            <dd className="text-content-muted">
                              {recommendation.recommended_human_action}
                            </dd>
                          </div>
                          <div>
                            <dt className="font-semibold text-content">
                              Why prioritized
                            </dt>
                            <dd className="text-content-muted">
                              {recommendation.priority_reason}
                            </dd>
                          </div>
                        </dl>
                        {recommendation.related_recommendations.length > 0 && (
                          <div className="mt-4 rounded-md border border-stroke bg-surface p-3">
                            <p className="text-sm font-semibold text-content">
                              Related evidence under this root issue
                            </p>
                            <ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-content-muted">
                              {recommendation.related_recommendations.map((related) => (
                                <li key={related.recommendation_id}>
                                  <span className="font-medium text-content">
                                    {related.title}:
                                  </span>{" "}
                                  {related.measured_fact}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                        <div className="mt-4">
                          <p className="text-sm font-semibold text-content">
                            Priority factors
                          </p>
                          <ul className="mt-2 space-y-2 text-sm text-content-muted">
                            {recommendation.priority_factors.map((factor) => (
                              <li key={factor.factor}>
                                <span className="font-medium capitalize text-content">
                                  {factor.factor.replaceAll("_", " ")}
                                </span>{" "}
                                · {factor.available ? `+${factor.contribution}` : "not available"}
                                <span className="block text-xs">{factor.explanation}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div className="mt-4 text-sm text-content-muted">
                          <p>
                            <span className="font-semibold text-content">Decisions blocked:</span>{" "}
                            {recommendation.decisions_blocked.join(", ") || "None asserted"}
                          </p>
                          <p>
                            <span className="font-semibold text-content">What it unlocks:</span>{" "}
                            {recommendation.affected_capabilities.join(", ")}
                          </p>
                        </div>
                        <div className="mt-4 rounded-md border border-stroke p-3 text-xs text-content-muted">
                          <p>{recommendation.source_authority}</p>
                          <p>Coverage: {recommendation.coverage}</p>
                          <p>Confidence: {recommendation.confidence}</p>
                          <p>
                            Evidence as of {new Date(recommendation.evidence_as_of).toLocaleString()}
                          </p>
                          {recommendation.limitations.map((limitation) => (
                            <p key={limitation}>Limitation: {limitation}</p>
                          ))}
                        </div>
                        <p className="mt-3 text-sm text-content-muted">
                          Resolving this: {recommendation.improves_if_resolved}
                        </p>
                        <Link
                          className="mt-3 inline-flex min-h-11 items-center font-semibold text-action-primary hover:underline"
                          to={recommendation.drilldown_path}
                        >
                          {recommendation.action_destination}
                        </Link>
                      </li>
                    ))}
                  </ol>
                </section>
              );
            })}
            {evaluatedAt && (
              <p className="text-xs text-content-muted">
                Evaluated {new Date(evaluatedAt).toLocaleString()}
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
