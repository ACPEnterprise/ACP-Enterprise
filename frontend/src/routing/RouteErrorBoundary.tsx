import { isRouteErrorResponse, useRouteError } from "react-router";

export function RouteErrorBoundary() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error) && error.status === 404
    ? "The requested page could not be found."
    : "This workspace could not be displayed. Please return to the dashboard or try again.";
  return <main className="mx-auto max-w-xl p-6" role="main"><section className="rounded-xl border border-stroke bg-surface p-6"><h1 className="text-xl font-semibold">Unable to display this page</h1><p className="mt-3 text-content-muted">{message}</p><a className="mt-5 inline-flex min-h-11 items-center text-action-primary underline" href="/">Return to dashboard</a></section></main>;
}
