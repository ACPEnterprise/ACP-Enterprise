import { useState, type FormEvent } from "react";
import { Archive, Search } from "lucide-react";

import { useHcpCustomerSourceHistoryBySource, useHcpHistoricalCustomerSearch } from "../../hooks/useHcpSourceHistory";
import { Alert, Badge, Button, Card, EmptyState, Input, Spinner } from "../../ui";

export function HistoricalCustomerSearch() {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const search = useHcpHistoricalCustomerSearch(query);
  const history = useHcpCustomerSourceHistoryBySource(selectedSourceId);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSelectedSourceId(null);
    setQuery(input.trim());
  };

  return <Card className="p-ui-4 sm:p-ui-5">
    <div className="flex items-start gap-3"><Archive className="mt-1 text-action-primary" size={20} /><div><h3 className="font-semibold">Historical customer records</h3><p className="mt-1 text-sm text-content-muted">Search sealed historical customers and service locations even when no native Customer record has been admitted.</p></div></div>
    <Alert variant="information" className="mt-4">Historical source evidence is read-only. It is not a native Customer record and cannot be edited, scheduled, invoiced, or used for financial posting.</Alert>
    <form className="mt-4 flex flex-col gap-3 sm:flex-row" onSubmit={submit}>
      <label className="relative min-w-0 flex-1"><span className="sr-only">Search historical customers</span><Search className="pointer-events-none absolute left-3 top-3 text-content-muted" size={18} /><Input aria-label="Search historical customers" className="pl-10" minLength={2} required value={input} onChange={(event) => setInput(event.target.value)} placeholder="Historical name, email, phone, address, or source ID" /></label>
      <Button type="submit">Search history</Button>
    </form>

    {search.isLoading && <div className="mt-4"><Spinner label="Searching historical customer records" /></div>}
    {search.isError && <div className="mt-4"><Alert variant="warning" title="Historical records unavailable">The sealed historical source could not be searched. Native Customer search remains separate.</Alert></div>}
    {search.data?.items.length === 0 && <div className="mt-4"><EmptyState title="No historical customers match." description="Try a different name, source ID, contact value, or service address." /></div>}
    {search.data && search.data.items.length > 0 && <div className="mt-4 space-y-3"><p className="text-xs text-content-muted">{search.data.match_count} source-backed match{search.data.match_count === 1 ? "" : "es"}{search.data.limited ? " · showing the first 20" : ""}</p><ul className="divide-y divide-stroke rounded-lg border border-stroke">{search.data.items.map((item) => <li className="p-3" key={item.source_customer_id}><button className="min-h-11 w-full text-left" type="button" onClick={() => setSelectedSourceId(item.source_customer_id)}><span className="flex flex-wrap items-center gap-2"><strong>{item.display_name}</strong><Badge variant="information">HISTORICAL ONLY</Badge></span><span className="mt-1 block text-sm text-content-muted">{item.primary_location ?? "Location unavailable"}</span><span className="mt-1 block text-xs text-content-muted">Source ID {item.source_customer_id}</span></button></li>)}</ul></div>}

    {history.isLoading && <div className="mt-4"><Spinner label="Loading historical customer journey" /></div>}
    {history.isError && <div className="mt-4"><Alert variant="warning">The selected historical journey is unavailable or requires additional financial read permission.</Alert></div>}
    {history.data && <section aria-label="Historical customer journey" className="mt-4 rounded-lg border border-stroke bg-surface-subtle p-4"><div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-semibold">Historical customer journey</h4><Badge variant="information">SOURCE BACKED</Badge></div><p className="mt-1 text-xs text-content-muted">HCP source ID {history.data.source_customer_id} · no mutation authority</p><dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-3 lg:grid-cols-6"><div><dt className="text-content-muted">Locations</dt><dd className="font-semibold">{history.data.counts.locations}</dd></div><div><dt className="text-content-muted">Jobs</dt><dd className="font-semibold">{history.data.counts.jobs}</dd></div><div><dt className="text-content-muted">Appointments</dt><dd className="font-semibold">{history.data.counts.appointments}</dd></div><div><dt className="text-content-muted">Estimates</dt><dd className="font-semibold">{history.data.counts.estimates}</dd></div><div><dt className="text-content-muted">Invoices</dt><dd className="font-semibold">{history.data.counts.invoices}</dd></div><div><dt className="text-content-muted">Payments</dt><dd className="font-semibold">{history.data.counts.payments}</dd></div></dl><div className="mt-4 grid gap-3 lg:grid-cols-2">{history.data.locations.map((location) => <article className="rounded-lg bg-surface p-3" key={location.source_id}><h5 className="font-medium">{location.address ?? "Address unavailable"}</h5><p className="text-sm text-content-muted">{[location.city, location.state, location.postal_code].filter(Boolean).join(", ")}</p><p className="mt-1 text-xs text-content-muted">Source Location {location.source_id}</p></article>)}</div></section>}
  </Card>;
}
