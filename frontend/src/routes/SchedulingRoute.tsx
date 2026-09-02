import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Search,
  UserRound,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { getOperatorApiError } from "../api/errors";
import { useAuth, useHasPermission } from "../auth";
import { DispatchAssignmentPanel } from "../components/dispatch/DispatchAssignmentPanel";
import { DispatchRecommendationPanel } from "../components/dispatch/DispatchRecommendationPanel";
import {
  dayRange,
  localDateValue,
  moveDate,
  operationalJobStatuses,
} from "../components/dispatch/dispatchPresentation";
import { useDispatchBoard } from "../hooks/useDispatch";
import { useJobs } from "../hooks/useJobs";
import {
  useAppointments,
  useRescheduleAppointment,
} from "../hooks/useScheduling";
import { appointmentDetailPath, jobDetailPath } from "../routing/paths";
import type { DispatchBoardItem } from "../types/dispatch";
import type { JobListItem } from "../types/jobs";
import type { AppointmentDetail, AppointmentStatus } from "../types/scheduling";
import { Alert, Badge, Button, Card, Input, Select, Spinner } from "../ui";

const START_HOUR = 7;
const END_HOUR = 19;
const MINUTES_VISIBLE = (END_HOUR - START_HOUR) * 60;
const statuses: readonly AppointmentStatus[] = [
  "draft",
  "scheduled",
  "confirmed",
  "completed",
  "cancelled",
  "no_show",
];
type View = "day" | "week";

const label = (value: string) => value.replaceAll("_", " ");
const time = (value: string | null) =>
  value
    ? new Date(value).toLocaleTimeString([], {
        hour: "numeric",
        minute: "2-digit",
      })
    : "Time unknown";
const toLocalInput = (value: string | null) => {
  if (!value) return "";
  const date = new Date(value);
  const number = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${number(date.getMonth() + 1)}-${number(date.getDate())}T${number(date.getHours())}:${number(date.getMinutes())}`;
};

function weekRange(date: string) {
  const selected = new Date(`${date}T12:00:00`);
  const start = new Date(selected);
  start.setDate(selected.getDate() - selected.getDay());
  const end = new Date(start);
  end.setDate(start.getDate() + 7);
  return {
    startAt: new Date(
      start.getFullYear(),
      start.getMonth(),
      start.getDate(),
    ).toISOString(),
    endAt: new Date(
      end.getFullYear(),
      end.getMonth(),
      end.getDate(),
    ).toISOString(),
  };
}

function appointmentState(
  item: AppointmentDetail,
  dispatch?: DispatchBoardItem,
  job?: JobListItem,
) {
  if (item.status === "cancelled") return "CANCELED";
  if (item.status === "completed" || job?.status === "completed")
    return "COMPLETED";
  if (job?.status === "cancelled") return "CANCELED";
  if (job?.status === "in_progress") return "IN PROGRESS";
  if (job?.status === "paused") return "PAUSED";
  if (dispatch?.assignment?.arrival_state === "arrived") return "ARRIVED";
  if (dispatch?.assignment?.arrival_state === "en_route") return "EN ROUTE";
  return item.status === "draft"
    ? "NEEDS SCHEDULING"
    : dispatch?.assignment
      ? "SCHEDULED"
      : "UNASSIGNED";
}

export function SchedulingRoute() {
  const { activeCompany } = useAuth();
  const canRead = useHasPermission("COMPANY_SCHEDULING_READ");
  const canManage = useHasPermission("COMPANY_SCHEDULING_MANAGE");
  const canDispatch = useHasPermission("COMPANY_DISPATCH_READ");
  const canDispatchManage = useHasPermission("COMPANY_DISPATCH_MANAGE");
  const canReadJobs = useHasPermission("COMPANY_JOB_READ");
  const [date, setDate] = useState(() => localDateValue(new Date()));
  const [view, setView] = useState<View>("day");
  const [branchId, setBranchId] = useState("");
  const [status, setStatus] = useState<AppointmentStatus | "">("");
  const [technician, setTechnician] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<AppointmentDetail | null>(null);
  const range = view === "day" ? dayRange(date) : weekRange(date);
  const appointments = useAppointments(
    {
      startAt: range.startAt,
      endAt: range.endAt,
      branchId: branchId || undefined,
      status: status ? [status] : undefined,
      page: 1,
      pageSize: 100,
    },
    Boolean(activeCompany) && canRead,
  );
  const dispatch = useDispatchBoard(
    range.startAt,
    range.endAt,
    branchId || undefined,
    Boolean(activeCompany) && canDispatch,
  );
  const jobs = useJobs(
    {
      branchId: branchId || undefined,
      status: operationalJobStatuses,
      page: 1,
      pageSize: 100,
      sortField: "priority",
      sortDirection: "desc",
    },
    Boolean(activeCompany) && canReadJobs,
  );
  const dispatchByAppointment = useMemo(
    () =>
      new Map(
        (dispatch.data?.items ?? []).map((item) => [item.appointment_id, item]),
      ),
    [dispatch.data?.items],
  );
  const jobsById = useMemo(
    () => new Map((jobs.data?.items ?? []).map((job) => [job.id, job])),
    [jobs.data?.items],
  );
  const technicians = useMemo(
    () =>
      Array.from(
        new Set(
          (dispatch.data?.items ?? [])
            .map((item) => item.assignment?.primary_employee_name)
            .filter((name): name is string => Boolean(name)),
        ),
      ).sort(),
    [dispatch.data?.items],
  );
  const visible = useMemo(
    () =>
      (appointments.data?.items ?? []).filter((item) => {
        const dispatchItem = dispatchByAppointment.get(item.id);
        const job = dispatchItem?.job_id
          ? jobsById.get(dispatchItem.job_id)
          : undefined;
        const haystack =
          `${item.appointment_number} ${job?.job_number ?? ""} ${job?.customer_display_name ?? ""} ${job?.service_location_label ?? ""}`.toLowerCase();
        const assignedName = dispatchItem?.assignment?.primary_employee_name;
        const matchesTechnician =
          !technician ||
          (technician === "__unassigned"
            ? !assignedName
            : assignedName === technician);
        return (
          matchesTechnician &&
          (!search.trim() || haystack.includes(search.trim().toLowerCase()))
        );
      }),
    [
      appointments.data?.items,
      dispatchByAppointment,
      jobsById,
      search,
      technician,
    ],
  );
  const selectedDispatch = selected
    ? dispatchByAppointment.get(selected.id)
    : undefined;

  if (!activeCompany)
    return (
      <Alert variant="danger" title="Company scope unavailable">
        Select an accessible Company before opening Scheduling.
      </Alert>
    );
  if (!canRead)
    return (
      <Alert variant="danger">You are not authorized to view Scheduling.</Alert>
    );
  const move = (amount: number) =>
    setDate(moveDate(date, amount * (view === "week" ? 7 : 1)));

  return (
    <div className="min-w-0 space-y-5 pb-12">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-action-primary">
            Office operations
          </p>
          <h1 className="mt-1 text-2xl font-bold sm:text-3xl">
            Schedule & Dispatch
          </h1>
          <p className="mt-2 text-content-muted">
            See when work happens, who owns it, and what still needs scheduling
            or assignment.
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            className="inline-flex min-h-11 items-center rounded-lg border border-stroke px-4 font-semibold"
            to="/jobs"
          >
            Create or open Job
          </Link>
          <Link
            className="inline-flex min-h-11 items-center rounded-lg bg-action-primary px-4 font-semibold text-white"
            to="/dispatch"
          >
            Open Dispatch
          </Link>
        </div>
      </header>
      <Card className="space-y-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              aria-label={`Previous ${view}`}
              onClick={() => move(-1)}
            >
              <ChevronLeft size={18} />
            </Button>
            <Button
              variant="outline"
              onClick={() => setDate(localDateValue(new Date()))}
            >
              Today
            </Button>
            <Button
              variant="outline"
              aria-label={`Next ${view}`}
              onClick={() => move(1)}
            >
              <ChevronRight size={18} />
            </Button>
            <Input
              className="w-auto"
              aria-label="Service date"
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
            />
          </div>
          <div
            className="grid grid-cols-2 rounded-lg border border-stroke p-1"
            aria-label="Calendar view"
          >
            <Button
              variant={view === "day" ? "primary" : "ghost"}
              onClick={() => setView("day")}
            >
              Day
            </Button>
            <Button
              variant={view === "week" ? "primary" : "ghost"}
              onClick={() => setView("week")}
            >
              Week
            </Button>
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-4">
          <label className="text-sm font-medium">
            Branch
            <Select
              className="mt-1"
              aria-label="Branch"
              value={branchId}
              onChange={(event) => setBranchId(event.target.value)}
            >
              <option value="">All accessible Branches</option>
              {activeCompany.branches.map((branch) => (
                <option key={branch.id} value={branch.id}>
                  {branch.name}
                </option>
              ))}
            </Select>
          </label>
          <label className="text-sm font-medium">
            Technician
            <Select
              className="mt-1"
              aria-label="Technician"
              value={technician}
              onChange={(event) => setTechnician(event.target.value)}
            >
              <option value="">All technicians</option>
              <option value="__unassigned">Unassigned only</option>
              {technicians.map((name) => (
                <option key={name}>{name}</option>
              ))}
            </Select>
          </label>
          <label className="text-sm font-medium">
            Status
            <Select
              className="mt-1"
              aria-label="Appointment status"
              value={status}
              onChange={(event) =>
                setStatus(event.target.value as AppointmentStatus | "")
              }
            >
              <option value="">All statuses</option>
              {statuses.map((value) => (
                <option key={value} value={value}>
                  {label(value)}
                </option>
              ))}
            </Select>
          </label>
          <label className="text-sm font-medium">
            Search
            <span className="relative mt-1 block">
              <Search
                className="absolute left-3 top-3 text-content-muted"
                size={17}
              />
              <Input
                className="pl-9"
                aria-label="Search schedule"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Job, Customer, Location"
              />
            </span>
          </label>
        </div>
      </Card>
      {(appointments.isLoading || dispatch.isLoading) && (
        <Card className="p-8">
          <Spinner label="Loading calendar" />
        </Card>
      )}
      {(appointments.isError || (canDispatch && dispatch.isError)) && (
        <Alert variant="danger" title="Schedule unavailable">
          {
            getOperatorApiError(
              appointments.error ?? dispatch.error,
              "Schedule",
            ).message
          }
        </Alert>
      )}
      {!appointments.isLoading &&
        !appointments.isError &&
        (view === "day" ? (
          <DayCalendar
            items={visible}
            dispatchByAppointment={dispatchByAppointment}
            jobsById={jobsById}
            onSelect={setSelected}
          />
        ) : (
          <WeekCalendar
            date={date}
            items={visible}
            dispatchByAppointment={dispatchByAppointment}
            jobsById={jobsById}
            onSelect={setSelected}
          />
        ))}
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_24rem]">
        <UnscheduledQueue jobs={jobs.data?.items ?? []} />
        {selected ? (
          <AppointmentPanel
            appointment={selected}
            dispatchItem={selectedDispatch}
            job={
              selectedDispatch?.job_id
                ? jobsById.get(selectedDispatch.job_id)
                : undefined
            }
            canManage={canManage}
            onClose={() => setSelected(null)}
          />
        ) : (
          <Card className="p-6">
            <CalendarDays />
            <h2 className="mt-3 text-lg font-semibold">Appointment details</h2>
            <p className="mt-2 text-sm text-content-muted">
              Select work on the calendar to inspect Customer, Location, Job,
              timing, assignment, and field state.
            </p>
          </Card>
        )}
      </section>
      {selectedDispatch && canDispatchManage && (
        <DispatchAssignmentPanel
          item={selectedDispatch}
          onClose={() => setSelected(null)}
        />
      )}
      {selectedDispatch && canDispatch && (
        <DispatchRecommendationPanel item={selectedDispatch} />
      )}
    </div>
  );
}

function DayCalendar({
  items,
  dispatchByAppointment,
  jobsById,
  onSelect,
}: {
  readonly items: readonly AppointmentDetail[];
  readonly dispatchByAppointment: Map<string, DispatchBoardItem>;
  readonly jobsById: Map<string, JobListItem>;
  readonly onSelect: (item: AppointmentDetail) => void;
}) {
  const lanes = useMemo(() => {
    const names = Array.from(
      new Set(
        items.map(
          (item) =>
            dispatchByAppointment.get(item.id)?.assignment
              ?.primary_employee_name ?? "Unassigned",
        ),
      ),
    ).sort((a, b) =>
      a === "Unassigned" ? -1 : b === "Unassigned" ? 1 : a.localeCompare(b),
    );
    return names.length ? names : ["Unassigned"];
  }, [dispatchByAppointment, items]);
  if (!items.length)
    return (
      <Card className="p-8 text-center">
        <Clock3 className="mx-auto text-content-muted" />
        <h2 className="mt-3 text-xl font-semibold">
          No scheduled appointments
        </h2>
        <p className="mt-2 text-content-muted">
          This is a valid empty day for the selected Branch and filters.
        </p>
      </Card>
    );
  return (
    <>
      <section aria-label="Day agenda" className="space-y-2 md:hidden">
        {items.map((item) => {
          const dispatch = dispatchByAppointment.get(item.id);
          const job = dispatch?.job_id
            ? jobsById.get(dispatch.job_id)
            : undefined;
          return (
            <button
              type="button"
              onClick={() => onSelect(item)}
              className="w-full rounded-xl border border-stroke bg-surface p-4 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus"
              key={item.id}
            >
              <span className="flex items-center justify-between gap-3">
                <strong>{time(item.arrival_window_start_at)}</strong>
                <Badge>{appointmentState(item, dispatch, job)}</Badge>
              </span>
              <span className="mt-2 block font-semibold">
                {job?.job_number ?? item.appointment_number}
              </span>
              <span className="block truncate text-sm">
                {job?.customer_display_name ?? "Customer context unavailable"}
              </span>
              <span className="block truncate text-xs text-content-muted">
                {job?.service_location_label ?? "Location context unavailable"}{" "}
                · {dispatch?.assignment?.primary_employee_name ?? "Unassigned"}
              </span>
            </button>
          );
        })}
      </section>
      <section
        aria-label="Day calendar"
        className="hidden overflow-x-auto rounded-xl border border-stroke bg-surface md:block"
      >
        <div
          className="min-w-[760px]"
          style={{
            gridTemplateColumns: `5rem repeat(${lanes.length}, minmax(12rem, 1fr))`,
          }}
        >
          <div
            className="grid border-b border-stroke bg-surface-subtle"
            style={{
              gridTemplateColumns: `5rem repeat(${lanes.length}, minmax(12rem, 1fr))`,
            }}
          >
            <div className="p-3 text-xs font-semibold text-content-muted">
              Time
            </div>
            {lanes.map((lane) => (
              <div
                className="border-l border-stroke p-3 font-semibold"
                key={lane}
              >
                <UserRound className="mr-2 inline" size={16} />
                {lane}
              </div>
            ))}
          </div>
          <div className="relative" style={{ height: `${MINUTES_VISIBLE}px` }}>
            {Array.from({ length: END_HOUR - START_HOUR + 1 }, (_, index) => (
              <div
                className="absolute inset-x-0 border-t border-stroke"
                style={{ top: `${index * 60}px` }}
                key={index}
              >
                <span className="absolute left-2 -translate-y-1/2 bg-surface pr-2 text-xs text-content-muted">
                  {new Date(2026, 0, 1, START_HOUR + index).toLocaleTimeString(
                    [],
                    { hour: "numeric" },
                  )}
                </span>
              </div>
            ))}
            <div className="absolute bottom-2 left-2 text-[11px] text-content-muted">
              Open space means unbooked time, not verified technician
              availability.
            </div>
            {items.map((item) => {
              const dispatch = dispatchByAppointment.get(item.id);
              const lane = Math.max(
                0,
                lanes.indexOf(
                  dispatch?.assignment?.primary_employee_name ?? "Unassigned",
                ),
              );
              const start = item.arrival_window_start_at
                ? new Date(item.arrival_window_start_at)
                : null;
              const startMinutes = start
                ? start.getHours() * 60 + start.getMinutes() - START_HOUR * 60
                : 0;
              const duration = Math.max(
                45,
                item.expected_duration_minutes ??
                  (item.arrival_window_start_at && item.arrival_window_end_at
                    ? (new Date(item.arrival_window_end_at).getTime() -
                        new Date(item.arrival_window_start_at).getTime()) /
                      60000
                    : 60),
              );
              const job = dispatch?.job_id
                ? jobsById.get(dispatch.job_id)
                : undefined;
              return (
                <button
                  type="button"
                  aria-label={`${item.appointment_number}, ${time(item.arrival_window_start_at)}, ${dispatch?.assignment?.primary_employee_name ?? "unassigned"}, ${appointmentState(item, dispatch, job)}`}
                  onClick={() => onSelect(item)}
                  key={item.id}
                  className="absolute overflow-hidden rounded-lg border border-action-primary/30 bg-action-primary/10 p-2 text-left shadow-sm hover:bg-action-primary/15 focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus"
                  style={{
                    top: `${Math.max(0, startMinutes)}px`,
                    height: `${Math.min(duration, MINUTES_VISIBLE - Math.max(0, startMinutes))}px`,
                    left: `calc(5rem + ${lane} * ((100% - 5rem) / ${lanes.length}) + .25rem)`,
                    width: `calc((100% - 5rem) / ${lanes.length} - .5rem)`,
                  }}
                >
                  <strong className="block truncate text-sm">
                    {job?.job_number ?? item.appointment_number}
                  </strong>
                  <span className="block truncate text-xs">
                    {job?.customer_display_name ??
                      "Customer context unavailable"}
                  </span>
                  <span className="block truncate text-xs text-content-muted">
                    {time(item.arrival_window_start_at)} ·{" "}
                    {appointmentState(item, dispatch, job)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </section>
    </>
  );
}

function WeekCalendar({
  date,
  items,
  dispatchByAppointment,
  jobsById,
  onSelect,
}: {
  readonly date: string;
  readonly items: readonly AppointmentDetail[];
  readonly dispatchByAppointment: Map<string, DispatchBoardItem>;
  readonly jobsById: Map<string, JobListItem>;
  readonly onSelect: (item: AppointmentDetail) => void;
}) {
  const days = Array.from({ length: 7 }, (_, index) => {
    const selected = new Date(`${date}T12:00:00`);
    const sunday = new Date(selected);
    sunday.setDate(selected.getDate() - selected.getDay() + index);
    return sunday;
  });
  return (
    <section
      aria-label="Week calendar"
      className="grid gap-3 md:grid-cols-2 xl:grid-cols-7"
    >
      {days.map((day) => {
        const rows = items.filter(
          (item) =>
            item.arrival_window_start_at &&
            new Date(item.arrival_window_start_at).toDateString() ===
              day.toDateString(),
        );
        return (
          <Card className="min-w-0 p-3" key={day.toISOString()}>
            <h2 className="font-semibold">
              {day.toLocaleDateString([], {
                weekday: "short",
                month: "short",
                day: "numeric",
              })}
            </h2>
            <div className="mt-3 space-y-2">
              {rows.map((item) => {
                const dispatch = dispatchByAppointment.get(item.id);
                const job = dispatch?.job_id
                  ? jobsById.get(dispatch.job_id)
                  : undefined;
                return (
                  <button
                    className="w-full rounded-lg border border-stroke p-2 text-left text-sm hover:border-action-primary"
                    onClick={() => onSelect(item)}
                    key={item.id}
                  >
                    <strong className="block truncate">
                      {time(item.arrival_window_start_at)} ·{" "}
                      {job?.job_number ?? item.appointment_number}
                    </strong>
                    <span className="block truncate text-xs text-content-muted">
                      {dispatch?.assignment?.primary_employee_name ??
                        "Unassigned"}
                    </span>
                  </button>
                );
              })}
              {!rows.length && (
                <p className="text-xs text-content-muted">No appointments</p>
              )}
            </div>
          </Card>
        );
      })}
    </section>
  );
}

function UnscheduledQueue({ jobs }: { readonly jobs: readonly JobListItem[] }) {
  const rows = jobs.filter((job) => !job.earliest_appointment_start_at);
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Needs scheduling</h2>
          <p className="text-sm text-content-muted">
            Authorized Jobs with no known Appointment time.
          </p>
        </div>
        <Badge>{rows.length}</Badge>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {rows.slice(0, 12).map((job) => (
          <Link
            className="rounded-lg border border-stroke p-3 hover:border-action-primary"
            to={jobDetailPath(job.id)}
            key={job.id}
          >
            <strong>{job.job_number}</strong>
            <span className="block truncate text-sm">
              {job.customer_display_name}
            </span>
            <span className="block truncate text-xs text-content-muted">
              {job.service_location_label} · {label(job.priority)}
            </span>
          </Link>
        ))}
        {!rows.length && (
          <p className="text-sm text-content-muted">
            No unscheduled Jobs in this scope.
          </p>
        )}
      </div>
      {rows.length > 12 && (
        <p className="mt-3 text-xs text-content-muted">
          Showing 12 of {rows.length}; refine Branch or open Jobs.
        </p>
      )}
    </Card>
  );
}

function AppointmentPanel({
  appointment,
  dispatchItem,
  job,
  canManage,
  onClose,
}: {
  readonly appointment: AppointmentDetail;
  readonly dispatchItem?: DispatchBoardItem;
  readonly job?: JobListItem;
  readonly canManage: boolean;
  readonly onClose: () => void;
}) {
  const mutation = useRescheduleAppointment();
  const [start, setStart] = useState(() =>
    toLocalInput(appointment.arrival_window_start_at),
  );
  const [duration, setDuration] = useState(
    appointment.expected_duration_minutes ?? 60,
  );
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const startAt = new Date(start);
    const endAt = new Date(startAt.getTime() + duration * 60000);
    mutation.mutate({
      appointmentId: appointment.id,
      input: {
        expected_version: appointment.concurrency_version,
        arrival_window_start_at: startAt.toISOString(),
        arrival_window_end_at: endAt.toISOString(),
        expected_duration_minutes: duration,
        capacity_units: appointment.capacity_units ?? "1.00",
        reason_code: "operational_adjustment",
      },
    });
  };
  return (
    <Card className="p-4">
      <div className="flex justify-between gap-3">
        <div>
          <p className="text-sm text-action-primary">
            {appointment.appointment_number}
          </p>
          <h2 className="text-lg font-semibold">
            {job?.job_number ?? "Appointment details"}
          </h2>
        </div>
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      </div>
      <dl className="mt-4 grid gap-3 text-sm">
        <div>
          <dt className="text-content-muted">Customer</dt>
          <dd>
            {job?.customer_display_name ?? "Customer context unavailable"}
          </dd>
        </div>
        <div>
          <dt className="text-content-muted">Service Location</dt>
          <dd>
            {job?.service_location_label ?? "Location context unavailable"}
          </dd>
        </div>
        <div>
          <dt className="text-content-muted">Technician</dt>
          <dd>
            {dispatchItem?.assignment?.primary_employee_name ?? "Unassigned"}
          </dd>
        </div>
        <div>
          <dt className="text-content-muted">Operational state</dt>
          <dd>{appointmentState(appointment, dispatchItem, job)}</dd>
        </div>
      </dl>
      <div className="mt-4 flex flex-wrap gap-2">
        <Link
          className="inline-flex min-h-11 items-center rounded-lg border border-stroke px-3"
          to={appointmentDetailPath(appointment.id)}
        >
          Open Appointment
        </Link>
        {job && (
          <Link
            className="inline-flex min-h-11 items-center rounded-lg border border-stroke px-3"
            to={jobDetailPath(job.id)}
          >
            Open Job
          </Link>
        )}
      </div>
      {canManage && appointment.status !== "cancelled" && (
        <form
          className="mt-5 space-y-3 border-t border-stroke pt-4"
          onSubmit={submit}
        >
          <h3 className="font-semibold">Move appointment</h3>
          <p className="text-xs text-content-muted">
            Uses the authoritative Scheduling conflict, capacity, Branch,
            version, audit, and Event contract.
          </p>
          <label className="block text-sm font-medium">
            New start
            <Input
              className="mt-1"
              required
              type="datetime-local"
              value={start}
              onChange={(event) => setStart(event.target.value)}
            />
          </label>
          <label className="block text-sm font-medium">
            Duration in minutes
            <Input
              className="mt-1"
              required
              type="number"
              min={1}
              value={duration}
              onChange={(event) => setDuration(Number(event.target.value))}
            />
          </label>
          {mutation.isError && (
            <Alert variant="danger" title="Appointment not moved">
              {getOperatorApiError(mutation.error, "Scheduling").message}
            </Alert>
          )}
          {mutation.isSuccess && (
            <Alert variant="success">
              Appointment moved. Calendar and Dispatch evidence are refreshing.
            </Alert>
          )}
          <Button type="submit" loading={mutation.isPending}>
            Confirm new time
          </Button>
        </form>
      )}
    </Card>
  );
}
