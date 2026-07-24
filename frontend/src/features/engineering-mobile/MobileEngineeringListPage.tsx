import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { Alert, Badge, Button, EmptyState, Spinner } from "../../ui";
import { useMobileReviews } from "./hooks";
import {
  mobileEngineeringLabel,
  mobileEngineeringTimestamp,
  shortExpectedHead,
} from "./presentation";

export function MobileEngineeringListPage() {
  const [page, setPage] = useState(1);
  const query = useMobileReviews({ page, pageSize: 10 });

  return (
    <div className="mx-auto w-full max-w-5xl space-y-ui-5 overflow-x-hidden">
      <header>
        <p className="text-sm font-semibold text-blue-400">
          Engineering Control
        </p>
        <h1 className="mt-ui-1 text-2xl font-bold sm:text-3xl">
          Pending reviews
        </h1>
        <p className="mt-ui-2 text-sm text-content-muted">
          Review owner instructions from your phone. Approval never starts
          execution.
        </p>
      </header>

      <Alert variant="warning" title="Execution is not connected">
        This workspace cannot run workers, commit, push, merge, or deploy.
      </Alert>

      <section aria-label="Engineering reviews">
        {query.isLoading && (
          <div className="flex min-h-48 items-center justify-center">
            <Spinner label="Loading engineering reviews" />
          </div>
        )}
        {query.isError && (
          <Alert
            variant="danger"
            announcement="assertive"
            title="Reviews unavailable"
            action={
              <Button variant="outline" onClick={() => void query.refetch()}>
                Retry
              </Button>
            }
          >
            Your session may have expired, access may be restricted, or the
            service may be unavailable.
          </Alert>
        )}
        {query.data?.items.length === 0 && (
          <EmptyState
            title="No reviews found"
            description="There are no commands awaiting owner review."
          />
        )}
        {query.data && query.data.items.length > 0 && (
          <div className="grid gap-ui-3">
            {query.data.items.map((review) => (
              <article
                key={review.id}
                className="min-w-0 rounded-xl border border-stroke bg-surface p-ui-4"
              >
                <div className="flex min-w-0 flex-wrap items-start justify-between gap-ui-3">
                  <div className="min-w-0">
                    <Link
                      to={`/engineering/${review.id}`}
                      className="break-all text-lg font-bold text-blue-400 hover:underline"
                    >
                      {review.ecid}
                    </Link>
                    <p className="mt-ui-1 text-sm text-content-muted">
                      {mobileEngineeringLabel(review.command_type)}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-ui-2">
                    <Badge>
                      {mobileEngineeringLabel(review.approval_state)}
                    </Badge>
                    <Badge>Execution not connected</Badge>
                  </div>
                </div>
                <dl className="mt-ui-4 grid min-w-0 gap-ui-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-content-muted">Repository</dt>
                    <dd className="break-all">{review.repository_key}</dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Branch</dt>
                    <dd className="break-all">{review.expected_branch}</dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Expected HEAD</dt>
                    <dd className="font-mono">
                      {shortExpectedHead(review.expected_head)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Change level</dt>
                    <dd>
                      {review.requested_code_changes
                        ? "Uncommitted changes"
                        : "Inspection only"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Created</dt>
                    <dd>{mobileEngineeringTimestamp(review.created_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-content-muted">Expires</dt>
                    <dd>{mobileEngineeringTimestamp(review.expires_at)}</dd>
                  </div>
                </dl>
                <Link
                  to={`/engineering/${review.id}`}
                  className="mt-ui-4 inline-flex min-h-11 w-full items-center justify-center rounded-md border border-stroke-strong px-ui-4 text-sm font-semibold hover:bg-surface-muted sm:w-auto"
                  aria-label={`Review ${review.ecid}`}
                >
                  Review command
                </Link>
              </article>
            ))}
          </div>
        )}
      </section>

      {query.data && query.data.total_pages > 0 && (
        <nav
          className="flex flex-wrap items-center justify-between gap-ui-3 border-t border-stroke pt-ui-4"
          aria-label="Review pages"
        >
          <span className="text-sm text-content-muted">
            Page {query.data.page} of {query.data.total_pages} ·{" "}
            {query.data.total_count} reviews
          </span>
          <div className="flex gap-ui-2">
            <Button
              variant="outline"
              aria-label="Previous page"
              disabled={query.data.page <= 1}
              onClick={() => setPage(query.data.page - 1)}
            >
              <ChevronLeft size={18} />
            </Button>
            <Button
              variant="outline"
              aria-label="Next page"
              disabled={query.data.page >= query.data.total_pages}
              onClick={() => setPage(query.data.page + 1)}
            >
              <ChevronRight size={18} />
            </Button>
          </div>
        </nav>
      )}
    </div>
  );
}
