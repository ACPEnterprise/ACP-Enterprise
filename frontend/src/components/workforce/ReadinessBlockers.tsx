import { explainReadiness } from "../../features/workforce/readinessExplanation";

export function ReadinessBlockers({ blockers }: { blockers: string[] }) {
  if (blockers.length === 0) return null;
  return <ul className="mt-2 space-y-2" aria-label="Readiness actions">
    {blockers.map((code) => {
      const explanation = explainReadiness(code);
      return <li className="rounded-lg bg-surface-subtle p-3 text-sm" key={code}>
        <p><strong>Missing:</strong> {explanation.missing}</p>
        <p className="mt-1 text-content-muted"><strong>Who acts:</strong> {explanation.actor}</p>
        <p className="mt-1 text-content-muted"><strong>Then:</strong> {explanation.next}</p>
      </li>;
    })}
  </ul>;
}
