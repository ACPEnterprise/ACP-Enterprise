import { ChevronLeft, ChevronRight } from "lucide-react";

import type { AccessibleBranch } from "../../auth/companyTypes";
import { Button, Field, Input, Select } from "../../ui";
import { localDateValue, moveDate } from "./dispatchPresentation";

export function DispatchScopeControls({ date, branchId, branches, onDateChange, onBranchChange }: { readonly date: string; readonly branchId: string; readonly branches: readonly AccessibleBranch[]; readonly onDateChange: (value: string) => void; readonly onBranchChange: (value: string) => void }) {
  return <section aria-label="Dispatch scope" className="grid gap-3 rounded-xl border border-stroke bg-surface p-ui-4 sm:grid-cols-[auto_1fr_auto] sm:items-end">
    <div className="flex gap-2"><Button variant="outline" aria-label="Previous day" onClick={() => onDateChange(moveDate(date, -1))}><ChevronLeft size={18} /></Button><Button variant="outline" onClick={() => onDateChange(localDateValue(new Date()))}>Today</Button><Button variant="outline" aria-label="Next day" onClick={() => onDateChange(moveDate(date, 1))}><ChevronRight size={18} /></Button></div>
    <Field label="Dispatch date"><Input type="date" value={date} onChange={(event) => onDateChange(event.target.value)} /></Field>
    <Field label="Branch"><Select value={branchId} onChange={(event) => onBranchChange(event.target.value)}><option value="">All accessible Branches</option>{branches.map((branch) => <option key={branch.id} value={branch.id}>{branch.name} ({branch.code})</option>)}</Select></Field>
  </section>;
}
