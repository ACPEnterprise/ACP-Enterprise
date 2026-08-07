import { Alert, Button, Card } from "../ui";

export function RouteErrorBoundary() {
  return (
    <div className="mx-auto w-full max-w-2xl p-ui-4 sm:p-ui-6">
      <Card className="p-ui-4 sm:p-ui-6">
        <Alert variant="danger" title="This page could not be displayed">
          Customer data could not be rendered safely. Return to the workspace or
          reload after checking your connection.
        </Alert>
        <div className="mt-4 flex flex-col gap-3 sm:flex-row">
          <Button type="button" onClick={() => window.location.reload()}>
            Reload page
          </Button>
          <Button variant="outline" onClick={() => window.location.assign("/")}>
            Return to workspace
          </Button>
        </div>
      </Card>
    </div>
  );
}
