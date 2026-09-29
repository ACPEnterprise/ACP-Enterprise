import { type FormEvent, useEffect, useState } from "react";

import { useAuth } from "../../auth";
import { useBranchSchedulingPolicy, useConfigureBranchSchedulingPolicy } from "../../hooks/useScheduling";
import { Alert, Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Select, Spinner } from "../../ui";
import type { BranchSchedulingException, BranchWeeklyInterval } from "../../types/scheduling";

const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const toMinutes = (value: string) => { const [hours, minutes] = value.split(":").map(Number); return hours * 60 + minutes; };
const toTime = (value: number) => `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
const blockerLabel: Record<string, string> = {
  NO_ACTIVE_CALENDAR: "No active calendar",
  NO_OPERATING_HOURS: "No operating hours configured",
  CAPACITY_NOT_CONFIGURED: "Capacity missing",
};

export function BranchSchedulingSetup() {
  const { activeCompany } = useAuth();
  const [branchId, setBranchId] = useState(activeCompany?.default_branch_id ?? activeCompany?.branches[0]?.id ?? "");
  const policy = useBranchSchedulingPolicy(branchId || undefined);
  const save = useConfigureBranchSchedulingPolicy();
  const [active, setActive] = useState(false);
  const [timezone, setTimezone] = useState("");
  const [horizon, setHorizon] = useState("");
  const [notice, setNotice] = useState("");
  const [slot, setSlot] = useState("");
  const [capacity, setCapacity] = useState("");
  const [reason, setReason] = useState("");
  const [intervals, setIntervals] = useState<BranchWeeklyInterval[]>([]);
  const [exceptions, setExceptions] = useState<BranchSchedulingException[]>([]);

  useEffect(() => {
    if (!policy.data) return;
    // The server policy is the form's concurrency snapshot; reset all fields together
    // whenever that authoritative version or selected Branch changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setActive(policy.data.status === "ACTIVE");
    setTimezone(policy.data.timezone);
    setHorizon(policy.data.booking_horizon_days?.toString() ?? "");
    setNotice(policy.data.minimum_notice_minutes?.toString() ?? "");
    setSlot(policy.data.slot_interval_minutes?.toString() ?? "");
    setCapacity(policy.data.default_capacity_units ?? "");
    setIntervals([...policy.data.weekly_intervals]);
    setExceptions([...policy.data.exceptions]);
    setReason("");
  }, [policy.data]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    await save.mutateAsync({ branchId, input: {
      expected_version: policy.data?.version ?? null,
      timezone,
      active,
      booking_horizon_days: Number(horizon),
      minimum_notice_minutes: Number(notice),
      slot_interval_minutes: Number(slot),
      default_capacity_units: capacity,
      weekly_intervals: intervals,
      exceptions,
      reason,
    }});
  };

  return <Card id="branch-scheduling-setup">
    <CardHeader><CardTitle>Branch Scheduling Setup</CardTitle><CardDescription>Configure the selected Branch calendar, capacity, booking limits, and exceptions. No values are assumed.</CardDescription></CardHeader>
    <CardContent className="space-y-ui-4">
      <label><span className="text-body-s font-semibold">Branch</span><Select value={branchId} onChange={(event) => setBranchId(event.target.value)}>{activeCompany?.branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name}</option>)}</Select></label>
      {policy.isPending && <Spinner label="Loading Branch Scheduling setup" />}
      {policy.isError && <Alert variant="danger">Branch Scheduling setup could not be loaded.</Alert>}
      {policy.data && <>
        <div className="flex flex-wrap items-center gap-ui-2"><Badge variant={policy.data.readiness === "SCHEDULING_READY" ? "success" : "warning"}>{policy.data.readiness.replaceAll("_", " ")}</Badge></div>
        {policy.data.blockers.length > 0 && <Alert variant="warning"><ul>{policy.data.blockers.map((item) => <li key={item}>{blockerLabel[item] ?? item.replaceAll("_", " ")}</li>)}</ul></Alert>}
        <form className="space-y-ui-4" onSubmit={(event) => void submit(event)}>
          <label className="flex items-center gap-ui-2"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Active calendar</label>
          <label><span className="text-body-s font-semibold">Branch timezone</span><Input required value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="America/New_York" /></label>
          <div className="grid gap-ui-3 sm:grid-cols-2 lg:grid-cols-4">
            <label><span className="text-body-s font-semibold">Booking horizon (days)</span><Input required type="number" min="1" value={horizon} onChange={(event) => setHorizon(event.target.value)} /></label>
            <label><span className="text-body-s font-semibold">Minimum notice (minutes)</span><Input required type="number" min="0" value={notice} onChange={(event) => setNotice(event.target.value)} /></label>
            <label><span className="text-body-s font-semibold">Slot interval (minutes)</span><Input required type="number" min="1" value={slot} onChange={(event) => setSlot(event.target.value)} /></label>
            <label><span className="text-body-s font-semibold">Default capacity</span><Input required type="number" min="0.01" step="0.01" value={capacity} onChange={(event) => setCapacity(event.target.value)} /></label>
          </div>
          <section className="space-y-ui-2"><div className="flex justify-between"><h3 className="font-semibold">Weekly operating hours</h3><Button type="button" variant="outline" onClick={() => setIntervals([...intervals, { day_of_week: 0, start_minute: 540, end_minute: 1020, capacity_units: capacity || "1" }])}>Add interval</Button></div>
            {intervals.map((item, index) => <div className="grid gap-ui-2 rounded border border-stroke p-ui-3 sm:grid-cols-5" key={`${item.day_of_week}-${index}`}>
              <Select aria-label={`Day ${index + 1}`} value={item.day_of_week} onChange={(event) => setIntervals(intervals.map((row, at) => at === index ? {...row, day_of_week: Number(event.target.value)} : row))}>{days.map((day, dayIndex) => <option key={day} value={dayIndex}>{day}</option>)}</Select>
              <Input aria-label={`Start ${index + 1}`} type="time" value={toTime(item.start_minute)} onChange={(event) => setIntervals(intervals.map((row, at) => at === index ? {...row, start_minute: toMinutes(event.target.value)} : row))} />
              <Input aria-label={`End ${index + 1}`} type="time" value={toTime(item.end_minute)} onChange={(event) => setIntervals(intervals.map((row, at) => at === index ? {...row, end_minute: toMinutes(event.target.value)} : row))} />
              <Input aria-label={`Capacity ${index + 1}`} type="number" min="0.01" step="0.01" value={item.capacity_units} onChange={(event) => setIntervals(intervals.map((row, at) => at === index ? {...row, capacity_units: event.target.value} : row))} />
              <Button type="button" variant="outline" onClick={() => setIntervals(intervals.filter((_, at) => at !== index))}>Remove</Button>
            </div>)}
          </section>
          <section className="space-y-ui-2"><div className="flex justify-between"><h3 className="font-semibold">Exceptions</h3><Button type="button" variant="outline" onClick={() => setExceptions([...exceptions, { exception_date: "", start_minute: null, end_minute: null, is_closed: true, capacity_units: null, reason_code: "" }])}>Add exception</Button></div>
            {exceptions.map((item, index) => <div className="grid gap-ui-2 rounded border border-stroke p-ui-3 sm:grid-cols-4" key={index}>
              <Input aria-label={`Exception date ${index + 1}`} required type="date" value={item.exception_date} onChange={(event) => setExceptions(exceptions.map((row, at) => at === index ? {...row, exception_date: event.target.value} : row))} />
              <label className="flex items-center gap-ui-2"><input type="checkbox" checked={item.is_closed} onChange={(event) => setExceptions(exceptions.map((row, at) => at === index ? {...row, is_closed: event.target.checked, capacity_units: event.target.checked ? null : (capacity || "1") } : row))} /> Closed</label>
              <Input aria-label={`Exception reason ${index + 1}`} required placeholder="Reason" value={item.reason_code} onChange={(event) => setExceptions(exceptions.map((row, at) => at === index ? {...row, reason_code: event.target.value} : row))} />
              {!item.is_closed && <Input aria-label={`Exception capacity ${index + 1}`} required type="number" min="0.01" step="0.01" value={item.capacity_units ?? ""} onChange={(event) => setExceptions(exceptions.map((row, at) => at === index ? {...row, capacity_units: event.target.value} : row))} />}
              {!item.is_closed && <Input aria-label={`Exception start ${index + 1}`} type="time" value={item.start_minute === null ? "" : toTime(item.start_minute)} onChange={(event) => setExceptions(exceptions.map((row, at) => at === index ? {...row, start_minute: event.target.value ? toMinutes(event.target.value) : null} : row))} />}
              {!item.is_closed && <Input aria-label={`Exception end ${index + 1}`} type="time" value={item.end_minute === null ? "" : toTime(item.end_minute)} onChange={(event) => setExceptions(exceptions.map((row, at) => at === index ? {...row, end_minute: event.target.value ? toMinutes(event.target.value) : null} : row))} />}
              <Button type="button" variant="outline" onClick={() => setExceptions(exceptions.filter((_, at) => at !== index))}>Remove</Button>
            </div>)}
          </section>
          <label><span className="text-body-s font-semibold">Change reason</span><Input required minLength={3} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
          {save.isError && <Alert variant="danger">Scheduling policy was not saved. Refresh if another administrator changed it.</Alert>}
          {save.isSuccess && <Alert variant="success">Branch Scheduling setup saved.</Alert>}
          <Button type="submit" disabled={active && intervals.length === 0} loading={save.isPending} loadingLabel="Saving Scheduling setup">Save Scheduling Setup</Button>
        </form>
      </>}
    </CardContent>
  </Card>;
}
