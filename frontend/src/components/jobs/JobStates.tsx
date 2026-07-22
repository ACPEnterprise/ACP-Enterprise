import { Alert, Button, EmptyState, Spinner } from "../../ui";

export function JobsLoadingState() { return <div className="flex justify-center p-12"><Spinner label="Loading Jobs" /></div>; }
export function JobsEmptyState() { return <EmptyState title="No Jobs found" description="Adjust the filters or create a Job to begin operational work." />; }
export function JobsErrorState({ onRetry }: { readonly onRetry: () => void }) { return <Alert variant="danger" title="Unable to load Jobs" action={<Button onClick={onRetry}>Retry</Button>}>The request could not be completed. Check access and try again.</Alert>; }
