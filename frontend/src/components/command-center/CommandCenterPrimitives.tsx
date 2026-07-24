import type { ReactNode } from "react";

import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../ui";

export type IntegrationState =
  | "available"
  | "awaiting-integration"
  | "coming-soon"
  | "not-connected"
  | "no-data";

const statePresentation: Record<
  IntegrationState,
  { readonly label: string; readonly variant: "success" | "information" | "warning" | "neutral" }
> = {
  available: { label: "Architecture Available", variant: "success" },
  "awaiting-integration": { label: "Awaiting Integration", variant: "warning" },
  "coming-soon": { label: "Coming Soon", variant: "neutral" },
  "not-connected": { label: "Not Connected", variant: "warning" },
  "no-data": { label: "No Data Available", variant: "neutral" },
};

export function IntegrationStateBadge({ state }: { readonly state: IntegrationState }) {
  const presentation = statePresentation[state];
  return (
    <Badge role="status" variant={presentation.variant}>
      {presentation.label}
    </Badge>
  );
}

export function CommandCenterPanel({
  title,
  description,
  action,
  children,
  className,
}: {
  readonly title: string;
  readonly description?: string;
  readonly action?: ReactNode;
  readonly children: ReactNode;
  readonly className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-ui-3">
        <div>
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function ExecutiveMetricCard({
  label,
  value,
  detail,
  state,
}: {
  readonly label: string;
  readonly value?: string;
  readonly detail: string;
  readonly state?: IntegrationState;
}) {
  return (
    <Card className="min-h-40 border-t-2 border-t-command-center-accent" elevation="none">
      <CardContent className="flex h-full flex-col justify-between pt-ui-5">
        <div>
          <p className="text-overline uppercase text-content-muted">{label}</p>
          <p className="mt-ui-3 text-heading-xl tracking-tight text-content">
            {value ?? statePresentation[state ?? "no-data"].label}
          </p>
        </div>
        <p className="mt-ui-4 text-body-s text-content-muted">{detail}</p>
      </CardContent>
    </Card>
  );
}

export function WorkforceRow({
  name,
  description,
  state,
}: {
  readonly name: string;
  readonly description: string;
  readonly state: IntegrationState;
}) {
  return (
    <li className="flex flex-col gap-ui-2 border-b border-stroke py-ui-3 last:border-0 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="font-semibold text-content">{name}</p>
        <p className="text-body-s text-content-muted">{description}</p>
      </div>
      <IntegrationStateBadge state={state} />
    </li>
  );
}
