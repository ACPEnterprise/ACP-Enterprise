import { useEffect, useRef, useState, type FormEvent } from "react";
import { Search, X } from "lucide-react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router";

import { Button, IconButton, Input } from "../../ui";
import { normalizeGlobalSearchQuery } from "./globalSearch";

interface GlobalSearchDialogProps {
  readonly onClose: () => void;
}

export function GlobalSearchDialog({ onClose }: GlobalSearchDialogProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const normalized = normalizeGlobalSearchQuery(query);
    if (!normalized) return;
    onClose();
    navigate(`/customers?query=${encodeURIComponent(normalized)}`);
  };

  return createPortal(
    <div
      className="safe-area-dialog fixed inset-0 z-[var(--layer-dialog)] bg-[var(--semantic-scrim)] p-4 sm:p-8"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="mx-auto mt-8 w-full max-w-2xl rounded-xl border border-stroke bg-surface p-4 shadow-2xl sm:mt-16 sm:p-6"
        role="dialog"
        aria-modal="true"
        aria-labelledby="global-search-title"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="global-search-title" className="text-heading-s text-content">Search customers and history</h2>
            <p className="mt-1 text-body-s text-content-muted">Use a name, phone, email, address, Customer number, or a short request such as “find Taylor history.”</p>
          </div>
          <IconButton icon={<X />} label="Close global search" variant="ghost" onClick={onClose} />
        </div>
        <form onSubmit={submit} className="mt-5 flex flex-col gap-3 sm:flex-row">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Search customers and history</span>
            <Search size={18} className="pointer-events-none absolute left-3 top-3 text-content-muted" aria-hidden="true" />
            <Input ref={inputRef} className="pl-10" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a customer or historical record" />
          </label>
          <Button type="submit" disabled={!normalizeGlobalSearchQuery(query)}>Search</Button>
        </form>
        <p className="mt-3 text-xs text-content-muted">Results open in the normal Customers workspace. Source provenance and history completeness stay secondary details.</p>
      </div>
    </div>,
    document.body,
  );
}
