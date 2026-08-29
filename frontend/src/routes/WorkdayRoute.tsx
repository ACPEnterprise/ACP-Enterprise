import {
  CalendarClock,
  CheckCircle2,
  Clock3,
  Coffee,
  LogOut,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  classifyWorkdayFailure,
  type PunchAction,
  type PunchState,
  type TimeEntry,
} from "../api/timekeeping";
import { useHasPermission } from "../auth/usePermissions";
import {
  useOwnPunch,
  useOwnTimecard,
  useOwnWorkdayState,
} from "../hooks/useWorkdayTime";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  Spinner,
} from "../ui";

const OWN_PUNCH = "COMPANY_TIMEKEEPING_OWN_PUNCH";
const OWN_READ = "COMPANY_TIMEKEEPING_OWN_READ";

const actionPresentation: Record<
  PunchAction,
  { label: string; pending: string; icon: typeof Clock3; variant: "primary" | "outline" }
> = {
  clock_in: { label: "Clock In", pending: "Clocking in", icon: Clock3, variant: "primary" },
  break_start: { label: "Start Break", pending: "Starting break", icon: Coffee, variant: "outline" },
  break_end: { label: "End Break", pending: "Ending break", icon: Coffee, variant: "primary" },
  clock_out: { label: "Clock Out", pending: "Clocking out", icon: LogOut, variant: "outline" },
};

function allowedActions(state: PunchState["state"]): readonly PunchAction[] {
  if (state === "not_clocked_in") return ["clock_in"];
  if (state === "on_break") return ["break_end"];
  return ["break_start", "clock_out"];
}

function stateCopy(state: PunchState) {
  if (state.state === "not_clocked_in") return { title: "Clocked out", detail: "You are not currently on the clock." };
  if (state.state === "on_break") return { title: "On break", detail: "Your workday remains open while your break is active." };
  return { title: "Clocked in", detail: "Your paid workday is active." };
}

function formatMoment(value: string | null, timezone?: string) {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(value));
}

function formatMinutes(value: number | null) {
  if (value === null) return "Pending";
  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

function provenanceLabel(entry: TimeEntry) {
  if (entry.supersedes_revision_id || entry.correction_reason) return "Corrected entry";
  return entry.provenance === "authorized_manual_entry" ? "Manager-entered time" : "Employee punch";
}

function AccessFailure({ failure, retry }: { failure: ReturnType<typeof classifyWorkdayFailure>; retry: () => void }) {
  const copy = failure === "employee_linkage_missing"
    ? { title: "Onboarding is incomplete", message: "Your authenticated account is not yet linked to an Employee record. Ask your Company administrator to complete onboarding." }
    : failure === "authentication_required"
      ? { title: "Sign in again", message: "Your session is no longer valid. Return to sign in before using the time clock." }
      : failure === "permission_denied"
        ? { title: "Timekeeping access is unavailable", message: "Your account does not currently have employee timekeeping access." }
        : { title: "Workday time is unavailable", message: "The authoritative timekeeping service could not be reached. No punch was recorded." };
  return (
    <Alert
      variant="danger"
      title={copy.title}
      icon={<ShieldAlert />}
      action={failure === "unavailable" || failure === "network_uncertain" ? <Button variant="outline" onClick={retry}>Retry</Button> : undefined}
    >
      {copy.message}
    </Alert>
  );
}

export function WorkdayRoute() {
  const canRead = useHasPermission(OWN_READ);
  const canPunch = useHasPermission(OWN_PUNCH);
  const state = useOwnWorkdayState(canRead);
  const timecard = useOwnTimecard(canRead);
  const punch = useOwnPunch();
  const refetchState = state.refetch;
  const refetchTimecard = timecard.refetch;
  const punchInFlight = useRef(false);
  const [notice, setNotice] = useState<"accepted" | "reconciling" | null>(null);

  useEffect(() => {
    const reconcile = () => {
      if (canRead) void refetchState();
    };
    window.addEventListener("online", reconcile);
    window.addEventListener("focus", reconcile);
    document.addEventListener("visibilitychange", reconcile);
    return () => {
      window.removeEventListener("online", reconcile);
      window.removeEventListener("focus", reconcile);
      document.removeEventListener("visibilitychange", reconcile);
    };
  }, [canRead, refetchState]);

  const actions = useMemo(
    () => (state.data ? allowedActions(state.data.state) : []),
    [state.data],
  );

  const submit = async (action: PunchAction) => {
    if (punchInFlight.current) return;
    punchInFlight.current = true;
    setNotice(null);
    try {
      await punch.mutateAsync(action);
      setNotice("accepted");
    } catch (error) {
      setNotice("reconciling");
      await refetchState();
      if (classifyWorkdayFailure(error) !== "network_uncertain") {
        await refetchTimecard();
      }
    } finally {
      punchInFlight.current = false;
    }
  };

  if (!canRead) {
    return (
      <div className="mx-auto max-w-xl p-ui-4 sm:p-ui-6">
        <AccessFailure failure="permission_denied" retry={() => undefined} />
      </div>
    );
  }

  const stateFailure = state.error ? classifyWorkdayFailure(state.error) : null;
  const copy = state.data ? stateCopy(state.data) : null;

  return (
    <div className="mx-auto w-full max-w-xl space-y-ui-5 p-ui-4 pb-ui-8 sm:p-ui-6">
      <header className="space-y-ui-1">
        <p className="text-body-s font-semibold text-action-primary">Workday Time</p>
        <h2 className="text-2xl font-bold sm:text-3xl">My time clock</h2>
        <p className="text-body-s text-content-muted">Server-confirmed paid-time evidence for your current workday.</p>
      </header>

      {state.isLoading && <div className="flex min-h-48 items-center justify-center"><Spinner label="Loading your current workday" size="large" /></div>}
      {stateFailure && <AccessFailure failure={stateFailure} retry={() => void refetchState()} />}

      {state.data && copy && (
        <Card elevation="medium" aria-labelledby="workday-current-state">
          <CardHeader className="text-center">
            <div className="mx-auto mb-ui-3 flex size-14 items-center justify-center rounded-full bg-action-primary/10 text-action-primary" aria-hidden="true">
              {state.data.state === "on_break" ? <Coffee /> : <Clock3 />}
            </div>
            <CardTitle id="workday-current-state" className="text-2xl">{copy.title}</CardTitle>
            <CardDescription>{copy.detail}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-ui-4">
            {state.data.occurred_at && (
              <p className="text-center text-body-s text-content-muted">
                Current state began <strong className="text-content">{formatMoment(state.data.occurred_at)}</strong>
              </p>
            )}
            {notice === "accepted" && (
              <Alert variant="success" announcement="polite" icon={<CheckCircle2 />} title="Punch accepted">
                The server confirmed your current workday state.
              </Alert>
            )}
            {notice === "reconciling" && (
              <Alert variant="warning" announcement="assertive" title="Confirming server state">
                The punch outcome was uncertain or the state changed. ACP reloaded authoritative server truth; review the status before trying again.
              </Alert>
            )}
            {!canPunch && (
              <Alert variant="warning" title="Punch permission unavailable">You may view your timecard, but your account cannot submit punches.</Alert>
            )}
            {canPunch && (
              <div className="grid gap-ui-3" aria-label="Available punch actions">
                {actions.map((action) => {
                  const presentation = actionPresentation[action];
                  const Icon = presentation.icon;
                  return (
                    <Button
                      key={action}
                      size="large"
                      variant={presentation.variant}
                      fullWidth
                      className="min-h-14 text-lg"
                      loading={punch.isPending}
                      loadingLabel={presentation.pending}
                      disabled={punch.isPending}
                      leadingIcon={<Icon />}
                      onClick={() => void submit(action)}
                    >
                      {presentation.label}
                    </Button>
                  );
                })}
              </div>
            )}
            <p className="text-center text-xs text-content-muted">Times and transitions are recorded by the server. This phone does not determine payable duration.</p>
          </CardContent>
        </Card>
      )}

      <section aria-labelledby="current-timecard-heading" className="space-y-ui-3">
        <div className="flex items-center justify-between gap-ui-3">
          <div>
            <h3 id="current-timecard-heading" className="text-heading-s">Current timecard</h3>
            <p className="text-body-s text-content-muted">
              {timecard.data?.pay_period
                ? `${timecard.data.pay_period.period_start} through ${timecard.data.pay_period.period_end}`
                : "Current authoritative entries"}
            </p>
          </div>
          <Button variant="ghost" size="small" leadingIcon={<RefreshCw />} disabled={timecard.isFetching} onClick={() => void refetchTimecard()}>
            Refresh
          </Button>
        </div>

        {timecard.isLoading && <Spinner label="Loading your timecard" />}
        {timecard.isError && (
          <Alert variant="warning" title="Timecard unavailable">Your current clock state may still be available. Refresh to try loading the timecard again.</Alert>
        )}
        {timecard.data?.entries.length === 0 && (
          <EmptyState icon={<CalendarClock />} title="No current-period entries" description="No authoritative time entries are available for this period." />
        )}
        {timecard.data && timecard.data.entries.length > 0 && (
          <ol className="space-y-ui-3">
            {timecard.data.entries.map((entry) => (
              <li key={entry.revision_id}>
                <Card elevation="none">
                  <CardContent className="space-y-ui-3 pt-ui-4 sm:pt-ui-6">
                    <div className="flex flex-wrap items-start justify-between gap-ui-2">
                      <div>
                        <p className="font-semibold">{entry.work_date}</p>
                        <p className="text-body-s text-content-muted">{provenanceLabel(entry)}</p>
                      </div>
                      <Badge variant={entry.state === "approved" ? "success" : entry.state === "corrected" ? "warning" : "neutral"}>{entry.state}</Badge>
                    </div>
                    <dl className="grid grid-cols-2 gap-ui-3 text-body-s">
                      <div><dt className="text-content-muted">Start</dt><dd>{formatMoment(entry.start_at, entry.timezone)}</dd></div>
                      <div><dt className="text-content-muted">End</dt><dd>{formatMoment(entry.end_at, entry.timezone)}</dd></div>
                      <div><dt className="text-content-muted">Approved duration</dt><dd>{formatMinutes(entry.approved_duration_minutes)}</dd></div>
                      <div><dt className="text-content-muted">Revision</dt><dd>{entry.revision_number}{entry.supersedes_revision_id ? " · corrected" : ""}</dd></div>
                    </dl>
                    {(entry.correction_reason || entry.state !== "approved") && (
                      <p className="text-body-s text-content-muted">
                        {entry.correction_reason
                          ? `Correction noted: ${entry.correction_reason}`
                          : "This entry is visible but is not yet approved Payroll time evidence."}
                      </p>
                    )}
                  </CardContent>
                </Card>
              </li>
            ))}
          </ol>
        )}
        <p className="text-body-s text-content-muted">See something incorrect? Contact an authorized manager. Employee editing is not enabled.</p>
      </section>
    </div>
  );
}
