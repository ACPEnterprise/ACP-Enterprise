import { Link } from "react-router";

import { Card, CardContent, CardDescription, CardHeader, CardTitle, Stack } from "../ui";

export function NotFoundRoute() {
  return (
    <Card className="mx-auto max-w-[var(--content-compact)]">
      <CardHeader>
        <CardTitle>Page not found</CardTitle>
        <CardDescription>The requested ACP Enterprise page does not exist or is not currently available.</CardDescription>
      </CardHeader>
      <CardContent>
        <Stack space="small">
          <Link className="w-fit rounded-md bg-action-primary px-ui-4 py-ui-3 font-semibold text-content-inverse hover:bg-action-primary-hover" to="/mission-control">
            Return to Mission Control
          </Link>
        </Stack>
      </CardContent>
    </Card>
  );
}
