import { CalendarDays, History, MapPin, RotateCw } from "lucide-react";
import { useState } from "react";
import { Link, useLocation } from "react-router";

import { getOperatorApiError } from "../api/errors";
import { TechnicianItineraryCard } from "../features/technician/TechnicianItineraryCard";
import { useTechnicianHistory, useTechnicianItinerary } from "../hooks/useTechnicianItinerary";
import { Alert, Badge, Button, Card, CardContent, EmptyState, Field, Input, Spinner } from "../ui";

function localDate(date: Date) {
  const offsetDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return offsetDate.toISOString().slice(0, 10);
}

export function TechnicianRoute() {
  const location = useLocation();
  const isJobs = location.pathname.endsWith("/jobs");
  const heading = location.pathname.endsWith("/schedule")
    ? "My Schedule"
    : location.pathname.endsWith("/jobs")
      ? "My Jobs"
      : "My day";
  const [serviceDate, setServiceDate] = useState(() => localDate(new Date()));
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyStart, setHistoryStart] = useState(() => {
    const start = new Date(); start.setDate(start.getDate() - 90); return localDate(start);
  });
  const [historyEnd, setHistoryEnd] = useState(() => localDate(new Date()));
  const itinerary = useTechnicianItinerary(serviceDate);
  const history = useTechnicianHistory(historyStart, historyEnd, historyQuery, isJobs);
  const itineraryError = itinerary.error
    ? getOperatorApiError(itinerary.error, "My day")
    : null;

  return (
    <div className="mx-auto w-full max-w-3xl space-y-ui-6 pb-ui-8">
      <header>
        <p className="text-sm font-medium text-action-primary">Field Service</p>
        <h2 className="mt-ui-1 text-2xl font-bold sm:text-3xl">{heading}</h2>
        <p className="mt-ui-2 text-content-muted">
          Your assigned visits in scheduled order.
        </p>
      </header>

      {isJobs && (
        <>
          <div className="grid gap-ui-3 sm:grid-cols-3">
            <Field label="Search your work" controlId="technician-history-search"><Input id="technician-history-search" placeholder="Customer, address, Job, service" value={historyQuery} onChange={(event) => setHistoryQuery(event.target.value)} /></Field>
            <Field label="From" controlId="technician-history-start"><Input id="technician-history-start" type="date" value={historyStart} onChange={(event) => setHistoryStart(event.target.value)} /></Field>
            <Field label="Through" controlId="technician-history-end"><Input id="technician-history-end" type="date" value={historyEnd} onChange={(event) => setHistoryEnd(event.target.value)} /></Field>
          </div>
          {history.isLoading && <Spinner label="Searching your Job history" size="large" />}
          {history.isError && <Alert variant="danger" title="History unavailable">Check the date range and try again. No company-wide records were searched.</Alert>}
          {history.isSuccess && history.data.items.length === 0 && <EmptyState icon={<History />} title="No matching work" description="No Jobs assigned to you match this search and date range." />}
          {history.isSuccess && history.data.items.length > 0 && (
            <section aria-labelledby="technician-history-heading">
              <h3 id="technician-history-heading" className="mb-ui-3 text-heading-s">History</h3>
              <ol className="grid gap-ui-3 sm:grid-cols-2">
                {history.data.items.map((item) => <li key={item.appointment_id}><Card><CardContent className="space-y-ui-2 pt-ui-4">
                  <div className="flex justify-between gap-ui-2"><p className="font-semibold">{item.customer_display_name}</p><Badge>{item.appointment_status.replaceAll("_", " ")}</Badge></div>
                  <p className="text-body-s text-content-muted">{item.service_date} · {item.job_number}</p>
                  <p className="flex gap-ui-2 text-body-s"><MapPin className="size-4 shrink-0" aria-hidden="true" />{item.service_location_label}</p>
                  <p className="text-body-s">{item.service_type?.replaceAll("_", " ") ?? "Service type unavailable"}</p>
                  <Link className="inline-flex min-h-11 items-center font-semibold text-action-primary" to={`/technician/jobs/${item.job_id}`}>Open field-safe Job detail</Link>
                </CardContent></Card></li>)}
              </ol>
            </section>
          )}
        </>
      )}

      {!isJobs && <div className="max-w-xs">
        <Field label="Service date" controlId="technician-service-date">
          <Input
            id="technician-service-date"
            type="date"
            value={serviceDate}
            onChange={(event) => setServiceDate(event.target.value)}
          />
        </Field>
      </div>}

      {!isJobs && itinerary.isLoading && <Spinner label="Loading your itinerary" size="large" />}
      {!isJobs && itinerary.isError && (
        <Alert
          variant="danger"
          title="My day could not load"
          action={
            <Button
              variant="outline"
              leadingIcon={<RotateCw />}
              onClick={() => void itinerary.refetch()}
            >
              Retry
            </Button>
          }
        >
          {itineraryError?.message ??
            "Check your connection and try again. No assignment changes were made."}
        </Alert>
      )}
      {!isJobs && itinerary.isSuccess && itinerary.data.items.length === 0 && (
        <EmptyState
          icon={<CalendarDays />}
          title="No assigned visits"
          description="There are no visits assigned to you for this service date."
        />
      )}
      {!isJobs && itinerary.isSuccess && itinerary.data.items.length > 0 && (
        <section aria-labelledby="technician-itinerary-heading">
          <div className="mb-ui-3 flex flex-wrap items-end justify-between gap-ui-2">
            <div>
              <h3 id="technician-itinerary-heading" className="text-heading-s">
                {itinerary.data.technician_display_name}&apos;s itinerary
              </h3>
              <p className="text-body-s text-content-muted">
                {itinerary.data.items.length} assigned {itinerary.data.items.length === 1 ? "visit" : "visits"}
              </p>
            </div>
          </div>
          <ol className="grid gap-ui-4 sm:grid-cols-2">
            {itinerary.data.items.map((item) => (
              <li key={item.appointment_id}>
                <TechnicianItineraryCard item={item} />
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
