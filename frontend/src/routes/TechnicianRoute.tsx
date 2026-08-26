import { CalendarDays, RotateCw } from "lucide-react";
import { useState } from "react";

import { TechnicianItineraryCard } from "../features/technician/TechnicianItineraryCard";
import { useTechnicianItinerary } from "../hooks/useTechnicianItinerary";
import { Alert, Button, EmptyState, Field, Input, Spinner } from "../ui";

function localDate(date: Date) {
  const offsetDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return offsetDate.toISOString().slice(0, 10);
}

export function TechnicianRoute() {
  const [serviceDate, setServiceDate] = useState(() => localDate(new Date()));
  const itinerary = useTechnicianItinerary(serviceDate);

  return (
    <div className="mx-auto w-full max-w-3xl space-y-ui-6 pb-ui-8">
      <header>
        <p className="text-sm font-medium text-action-primary">Field Service</p>
        <h2 className="mt-ui-1 text-2xl font-bold sm:text-3xl">My day</h2>
        <p className="mt-ui-2 text-content-muted">
          Your assigned visits in scheduled order.
        </p>
      </header>

      <div className="max-w-xs">
        <Field label="Service date" controlId="technician-service-date">
          <Input
            id="technician-service-date"
            type="date"
            value={serviceDate}
            onChange={(event) => setServiceDate(event.target.value)}
          />
        </Field>
      </div>

      {itinerary.isLoading && <Spinner label="Loading your itinerary" size="large" />}
      {itinerary.isError && (
        <Alert
          variant="danger"
          title="Your itinerary is unavailable"
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
          Check your connection and try again. No assignment changes were made.
        </Alert>
      )}
      {itinerary.isSuccess && itinerary.data.items.length === 0 && (
        <EmptyState
          icon={<CalendarDays />}
          title="No assigned visits"
          description="There are no visits assigned to you for this service date."
        />
      )}
      {itinerary.isSuccess && itinerary.data.items.length > 0 && (
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
