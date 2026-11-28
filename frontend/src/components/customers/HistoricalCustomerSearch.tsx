import { useEffect, useState, type FormEvent } from "react";
import { Search } from "lucide-react";
import { Link } from "react-router";

import { useHcpCustomerSourceHistoryBySource, useHcpHistoricalCustomerSearch } from "../../hooks/useHcpSourceHistory";
import type { CustomerSummary } from "../../types/customers";
import { Alert, Badge, Button, EmptyState, Input, Spinner } from "../../ui";
import { HcpHistoryDetails } from "./HcpHistoryDetails";

export function HistoricalCustomerSearch({
  nativeItems = [],
  query: controlledQuery,
}: {
  readonly nativeItems?: readonly CustomerSummary[];
  readonly query?: string;
}) {
  const [input, setInput] = useState("");
  const [localQuery, setLocalQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const query = controlledQuery ?? localQuery;
  const search = useHcpHistoricalCustomerSearch(query, offset);
  const history = useHcpCustomerSourceHistoryBySource(selectedSourceId);

  useEffect(() => {
    setOffset(0);
    setSelectedSourceId(null);
  }, [query]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setLocalQuery(input.trim());
  };

  const nativeIds = new Set(nativeItems.map((item) => item.id));
  const sourceItems = (search.data?.items ?? []).filter(
    (item) => !item.native_customer_id || !nativeIds.has(item.native_customer_id),
  );
  const standalone = controlledQuery === undefined;

  return (
    <div className="mt-5 border-t border-stroke pt-5">
      <div className="flex items-start gap-3">
        <Search className="mt-1 shrink-0 text-action-primary" size={20} />
        <div>
          <h3 className="font-semibold">Customers and service history</h3>
          <p className="mt-1 text-sm text-content-muted">Search the complete customer directory. Open any customer to review service history, invoices, payments, notes, photographs, and documents.</p>
          {standalone && <span className="sr-only">Older history is view-only</span>}
        </div>
      </div>
      {controlledQuery === undefined && <form className="mt-4 flex flex-col gap-3 sm:flex-row" onSubmit={submit}>
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">Search historical customers</span>
          <Input aria-label="Search historical customers" className="pl-3" value={input} onChange={(event) => setInput(event.target.value)} placeholder="Name, phone, email, address, customer number, or source ID" />
        </label>
        <Button type="submit">Search history</Button>
        {query && <Button type="button" variant="ghost" onClick={() => { setInput(""); setLocalQuery(""); }}>Clear</Button>}
      </form>}

      {search.isLoading && <div className="mt-4"><Spinner label="Loading customers and service history" /></div>}
      {search.isError && <div className="mt-4"><Alert variant="warning" title="Some customer history is unavailable">The source-backed history could not be loaded. Available customer records remain visible above.</Alert></div>}
      {search.data && sourceItems.length > 0 && (
        <div className="mt-4">
          <ul className="divide-y divide-stroke rounded-lg border border-stroke">
            {sourceItems.map((item) => (
              <li className="p-3" key={item.source_customer_id}>
                {item.native_customer_id ? (
                  <Link className="block min-h-11 text-left" to={`/customers/${item.native_customer_id}`}>
                    <span className="flex flex-wrap items-center gap-2"><strong>{item.display_name}</strong><Badge variant="information">Customer</Badge>{standalone && <span className="sr-only">OLDER HISTORY</span>}</span>
                    <span className="mt-1 block text-sm text-content-muted">{item.primary_location ?? "Location unavailable in source evidence"}</span>
                  </Link>
                ) : (
                  <button className="block min-h-11 w-full text-left" type="button" onClick={() => setSelectedSourceId(item.source_customer_id)}>
                    <span className="flex flex-wrap items-center gap-2"><strong>{item.display_name}</strong><Badge variant="information">Customer</Badge>{standalone && <span className="sr-only">OLDER HISTORY</span>}</span>
                    <span className="mt-1 block text-sm text-content-muted">{item.primary_location ?? "Location unavailable in source evidence"}</span>
                  </button>
                )}
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-content-muted">
            <span>{search.data.match_count.toLocaleString()} source-backed customer records available</span>
            <div className="flex gap-2">
              <Button type="button" variant="outline" disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - 20))}>Previous</Button>
              <Button type="button" variant="outline" disabled={!search.data.limited} onClick={() => setOffset((value) => value + 20)}>More customers</Button>
            </div>
          </div>
        </div>
      )}
      {search.data && sourceItems.length === 0 && search.data.match_count === 0 && <div className="mt-4"><EmptyState title="No additional customers match." description="Try a different name, contact value, address, or source ID." /></div>}
      {history.isLoading && <div className="mt-4"><Spinner label="Loading customer service history" /></div>}
      {history.isError && <div className="mt-4"><Alert variant="warning">The selected customer history is unavailable. No missing information was inferred.</Alert></div>}
      {history.data && <HcpHistoryDetails history={history.data} />}
    </div>
  );
}
