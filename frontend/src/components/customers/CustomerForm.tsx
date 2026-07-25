import { useState, type FormEvent } from "react";
import { AlertTriangle, Search } from "lucide-react";

import { getApiErrorMessage } from "../../api/errors";
import type {
  CustomerDetail,
  CustomerInput,
  DuplicateMatch,
} from "../../types/customers";

const inputClass =
  "mt-1 min-h-11 w-full rounded-lg border border-stroke-strong bg-surface px-3 py-2 text-sm text-content outline-none focus:border-action-primary focus-visible:ring-2 focus-visible:ring-focus";
const labelClass = "text-sm font-medium text-content-secondary";

const emptyCustomer: CustomerInput = {
  customer_type: "individual",
  first_name: "",
  last_name: "",
  business_name: "",
  primary_phone: "",
  secondary_phone: "",
  email: "",
  preferred_contact_method: "phone",
  status: "active",
  source: "unknown",
  is_vip: false,
  internal_notes: "",
};

function editableCustomer(customer?: CustomerDetail): CustomerInput {
  if (!customer) return emptyCustomer;
  return {
    customer_type: customer.customer_type,
    first_name: customer.first_name ?? "",
    last_name: customer.last_name ?? "",
    business_name: customer.business_name ?? "",
    primary_phone: customer.primary_phone,
    secondary_phone: customer.secondary_phone ?? "",
    email: customer.email ?? "",
    preferred_contact_method: customer.preferred_contact_method,
    status: customer.status,
    source: customer.source,
    is_vip: customer.is_vip,
    internal_notes: customer.internal_notes ?? "",
  };
}

function nullable(value: string | null): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

interface CustomerFormProps {
  customer?: CustomerDetail;
  duplicateWarnings?: DuplicateMatch[];
  isSaving: boolean;
  isCheckingDuplicates?: boolean;
  error?: unknown;
  onCheckDuplicates?: (input: CustomerInput) => void;
  onSubmit: (input: CustomerInput) => void;
  onCancel: () => void;
}

export function CustomerForm({
  customer,
  duplicateWarnings = [],
  isSaving,
  isCheckingDuplicates = false,
  error,
  onCheckDuplicates,
  onSubmit,
  onCancel,
}: CustomerFormProps) {
  const [form, setForm] = useState<CustomerInput>(() =>
    editableCustomer(customer),
  );
  const [validationError, setValidationError] = useState<string | null>(null);

  const update = <Key extends keyof CustomerInput>(
    key: Key,
    value: CustomerInput[Key],
  ) => setForm((current) => ({ ...current, [key]: value }));

  const validate = () => {
    if (form.customer_type === "individual" && (!form.first_name || !form.last_name)) {
      return "Individual customers require first and last name.";
    }
    if (form.customer_type === "business" && !form.business_name) {
      return "Business customers require a business name.";
    }
    if (!form.primary_phone.trim()) return "Primary phone is required.";
    if (form.preferred_contact_method === "email" && !form.email) {
      return "Email is required when email is preferred.";
    }
    return null;
  };

  const normalizedInput = (): CustomerInput => ({
    ...form,
    first_name: nullable(form.first_name),
    last_name: nullable(form.last_name),
    business_name: nullable(form.business_name),
    secondary_phone: nullable(form.secondary_phone),
    email: nullable(form.email),
    internal_notes: nullable(form.internal_notes),
    primary_phone: form.primary_phone.trim(),
    source: form.source.trim() || "unknown",
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const message = validate();
    setValidationError(message);
    if (!message) onSubmit(normalizedInput());
  };

  return (
    <form onSubmit={submit} className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2">
        <label className={labelClass}>
          Customer type
          <select
            className={inputClass}
            value={form.customer_type}
            onChange={(event) =>
              update("customer_type", event.target.value as CustomerInput["customer_type"])
            }
          >
            <option value="individual">Individual</option>
            <option value="business">Business</option>
          </select>
        </label>
        <label className={labelClass}>
          Business name
          <input
            className={inputClass}
            value={form.business_name ?? ""}
            onChange={(event) => update("business_name", event.target.value)}
            required={form.customer_type === "business"}
            maxLength={200}
          />
        </label>
        <label className={labelClass}>
          First name
          <input
            className={inputClass}
            value={form.first_name ?? ""}
            onChange={(event) => update("first_name", event.target.value)}
            required={form.customer_type === "individual"}
            maxLength={100}
          />
        </label>
        <label className={labelClass}>
          Last name
          <input
            className={inputClass}
            value={form.last_name ?? ""}
            onChange={(event) => update("last_name", event.target.value)}
            required={form.customer_type === "individual"}
            maxLength={100}
          />
        </label>
        <label className={labelClass}>
          Primary phone
          <input
            className={inputClass}
            type="tel"
            value={form.primary_phone}
            onChange={(event) => update("primary_phone", event.target.value)}
            required
            maxLength={30}
          />
        </label>
        <label className={labelClass}>
          Secondary phone
          <input
            className={inputClass}
            type="tel"
            value={form.secondary_phone ?? ""}
            onChange={(event) => update("secondary_phone", event.target.value)}
            maxLength={30}
          />
        </label>
        <label className={labelClass}>
          Email
          <input
            className={inputClass}
            type="email"
            value={form.email ?? ""}
            onChange={(event) => update("email", event.target.value)}
            required={form.preferred_contact_method === "email"}
            maxLength={320}
          />
        </label>
        <label className={labelClass}>
          Preferred contact
          <select
            className={inputClass}
            value={form.preferred_contact_method}
            onChange={(event) =>
              update(
                "preferred_contact_method",
                event.target.value as CustomerInput["preferred_contact_method"],
              )
            }
          >
            <option value="phone">Phone</option>
            <option value="sms">SMS</option>
            <option value="email">Email</option>
          </select>
        </label>
        <label className={labelClass}>
          Status
          <select
            className={inputClass}
            value={form.status}
            onChange={(event) =>
              update("status", event.target.value as CustomerInput["status"])
            }
          >
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="do_not_service">Do not service</option>
          </select>
        </label>
        <label className={labelClass}>
          Customer source
          <input
            className={inputClass}
            value={form.source}
            onChange={(event) => update("source", event.target.value)}
            required
            maxLength={50}
          />
        </label>
      </div>

      <label className={`${labelClass} block`}>
        Internal customer context
        <textarea
          className={`${inputClass} min-h-24`}
          value={form.internal_notes ?? ""}
          onChange={(event) => update("internal_notes", event.target.value)}
          maxLength={4000}
        />
      </label>

      <label className="flex min-h-11 items-center gap-3 text-sm text-content-secondary">
        <input
          type="checkbox"
          checked={form.is_vip}
          onChange={(event) => update("is_vip", event.target.checked)}
          className="h-5 w-5 rounded border-stroke-strong"
        />
        VIP customer
      </label>

      {duplicateWarnings.length > 0 && (
        <div className="rounded-xl border border-amber-700 bg-amber-950/40 p-4">
          <div className="flex items-center gap-2 font-semibold text-amber-300">
            <AlertTriangle size={18} /> Possible duplicate customers
          </div>
          <ul className="mt-3 space-y-2 text-sm text-amber-100">
            {duplicateWarnings.map((match) => (
              <li key={match.id}>
                {match.business_name || `${match.first_name ?? ""} ${match.last_name ?? ""}`.trim()} · {match.primary_phone} ({match.reasons.join(", ").replaceAll("_", " ")})
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-amber-300">
            Review these records before continuing. Records are never merged automatically.
          </p>
        </div>
      )}

      {(validationError || Boolean(error)) && (
        <div className="rounded-lg border border-red-900 bg-red-950/40 p-3 text-sm text-red-300">
          {validationError ?? getApiErrorMessage(error)}
        </div>
      )}

      <div className="grid gap-3 sm:flex sm:flex-wrap sm:justify-end">
        <button
          type="button"
          onClick={onCancel}
          className="min-h-11 rounded-lg border border-stroke-strong px-4 py-2 text-sm text-content-secondary"
        >
          Cancel
        </button>
        {!customer && onCheckDuplicates && (
          <button
            type="button"
            disabled={isCheckingDuplicates}
            onClick={() => {
              const message = validate();
              setValidationError(message);
              if (!message) onCheckDuplicates(normalizedInput());
            }}
            className="flex min-h-11 items-center justify-center gap-2 rounded-lg border border-action-primary px-4 py-2 text-sm text-action-primary disabled:opacity-50"
          >
            <Search size={16} />
            {isCheckingDuplicates ? "Checking…" : "Check duplicates"}
          </button>
        )}
        <button
          type="submit"
          disabled={isSaving}
          className="min-h-11 rounded-lg bg-action-primary px-5 py-2 text-sm font-semibold text-content-inverse disabled:opacity-50"
        >
          {isSaving ? "Saving…" : customer ? "Save customer" : "Create customer"}
        </button>
      </div>
    </form>
  );
}
