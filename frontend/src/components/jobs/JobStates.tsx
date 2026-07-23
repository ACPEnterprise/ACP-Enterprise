import { getOperatorApiError } from "../../api/errors";
import { Alert, Button, EmptyState, Spinner } from "../../ui";

export function JobsLoadingState() { return <div className="flex justify-center p-12"><Spinner label="Loading Jobs" /></div>; }
export function JobsEmptyState() { return <EmptyState title="No Jobs found" description="Adjust the filters or create a Job to begin operational work." />; }
export function JobsErrorState({ error, onRetry }: { readonly error?: unknown; readonly onRetry: () => void }) {
  const value = getOperatorApiError(error);
  return <Alert variant="danger" title={value.title} action={value.retryable ? <Button onClick={onRetry}>Retry</Button> : undefined}>{value.message}</Alert>;
}
