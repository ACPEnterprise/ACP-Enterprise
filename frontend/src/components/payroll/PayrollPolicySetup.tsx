import { useState, type FormEvent } from "react";
import { useHasPermission } from "../../auth";
import { Alert, Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../ui";
import { usePayrollPolicy, usePayrollPolicyActions } from "../../hooks/usePayroll";

const split = (value: FormDataEntryValue | null) => String(value ?? "").split(",").map((item) => item.trim()).filter(Boolean);

export function PayrollPolicySetup() {
  const canRead = useHasPermission("COMPANY_PAYROLL_POLICY_READ");
  const canManage = useHasPermission("COMPANY_PAYROLL_POLICY_MANAGE");
  const canApprove = useHasPermission("COMPANY_PAYROLL_POLICY_APPROVE");
  const policy = usePayrollPolicy(canRead);
  const actions = usePayrollPolicyActions();
  const [message, setMessage] = useState("");
  if (!canRead) return null;
  if (policy.isPending) return <Card><CardContent>Loading Payroll policy authority…</CardContent></Card>;
  if (policy.isError || !policy.data) return <Alert variant="danger" title="Payroll policy unavailable">No policy value was loaded or changed.</Alert>;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const overtimeEnabled = data.get("overtime_enabled") === "on";
    try {
      const result = await actions.draft.mutateAsync({
        policy_version: Number(data.get("policy_version")), effective_start: String(data.get("effective_start")), effective_end: String(data.get("effective_end") || "") || null,
        pay_frequency: String(data.get("pay_frequency")), schedule_definition_id: String(data.get("schedule_definition_id")), schedule_version: Number(data.get("schedule_version")), regular_earning_categories: split(data.get("regular_earning_categories")),
        overtime: overtimeEnabled ? { weekly_threshold_minutes: Number(data.get("weekly_threshold_minutes")), daily_threshold_minutes: null, multiplier: String(data.get("overtime_multiplier")), double_time_threshold_minutes: null, double_time_multiplier: null, workweek_start_day: Number(data.get("workweek_start_day")), workweek_start_time: String(data.get("workweek_start_time")), included_earning_categories: split(data.get("regular_earning_categories")), excluded_earning_categories: [] } : null,
        break_treatment: String(data.get("break_treatment")), leave_category_refs: split(data.get("leave_category_refs")), holiday_policy_ref: String(data.get("holiday_policy_ref") || "") || null, pto_policy_ref: String(data.get("pto_policy_ref") || "") || null,
        salaried_time_requirement: String(data.get("salaried_time_requirement")), minimum_increment_minutes: null, rounding_rule: null, pre_finalization_correction_treatment: String(data.get("pre_finalization_correction_treatment")), post_finalization_adjustment_treatment: String(data.get("post_finalization_adjustment_treatment")), post_payment_adjustment_treatment: String(data.get("post_payment_adjustment_treatment")), cutoff_rule: String(data.get("cutoff_rule")), required_time_approvals: Number(data.get("required_time_approvals")), compensation_authority_required: true,
        decision_evidence_digest: String(data.get("decision_evidence_digest")), audit_reason: String(data.get("audit_reason")), supersedes_policy_id: policy.data.policy?.id ?? null,
      });
      setMessage(`Draft policy version ${String(result.version)} saved. A different authorized approver must approve it.`);
      event.currentTarget.reset();
    } catch { setMessage("Policy draft was not saved. Review all required fields, dates, and authority."); }
  };
  return <Card id="payroll-policy-setup"><CardHeader><CardTitle>Payroll policy setup</CardTitle><CardDescription>Enter the Company policy that governs pay periods. No default pay frequency, overtime rule, or correction treatment is assumed.</CardDescription></CardHeader><CardContent className="space-y-4">
    {message && <Alert variant={message.includes("saved") ? "success" : "danger"}>{message}</Alert>}
    {policy.data.policy ? <div className="rounded-lg border border-stroke p-3 text-sm"><strong>Approved policy v{policy.data.policy.version}</strong> · effective {policy.data.policy.effective_start}{policy.data.policy.effective_end ? ` through ${policy.data.policy.effective_end}` : ""}</div> : <Alert variant="warning" title="Policy required">An authorized owner must draft a policy, then a different authorized approver must approve it.</Alert>}
    {policy.data.drafts.length > 0 && <div className="space-y-2"><h3 className="font-semibold">Draft policies awaiting approval</h3>{policy.data.drafts.map((draft) => <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-stroke p-2 text-sm" key={draft.id}><span>Version {draft.version} · effective {draft.effective_start} · {draft.reason}</span>{canApprove && <Button size="small" type="button" disabled={actions.approve.isPending} onClick={() => void actions.approve.mutateAsync(draft.id)}>Approve policy</Button>}</div>)}</div>}
    {canManage && <form className="grid gap-3 rounded-lg border border-stroke p-4 md:grid-cols-2" onSubmit={submit}><h3 className="font-semibold md:col-span-2">Draft a new Payroll policy</h3>
      <label>Policy version<input className="block w-full" name="policy_version" type="number" min="1" defaultValue="1" required /></label><label>Effective start<input className="block w-full" name="effective_start" type="date" required /></label><label>Effective end (optional)<input className="block w-full" name="effective_end" type="date" /></label><label>Pay frequency<select className="block w-full" name="pay_frequency" required><option value="">Select…</option><option value="weekly">Weekly</option><option value="biweekly">Biweekly</option><option value="semimonthly">Semimonthly</option><option value="monthly">Monthly</option></select></label>
      <label>Schedule definition ID<input className="block w-full" name="schedule_definition_id" required /></label><label>Schedule version<input className="block w-full" name="schedule_version" type="number" min="1" defaultValue="1" required /></label><label>Regular earning categories (comma separated)<input className="block w-full" name="regular_earning_categories" placeholder="regular_wages,overtime_wages" required /></label><label>Break treatment<input className="block w-full" name="break_treatment" required /></label>
      <label>Leave category references<input className="block w-full" name="leave_category_refs" /></label><label>Holiday policy reference<input className="block w-full" name="holiday_policy_ref" /></label><label>PTO policy reference<input className="block w-full" name="pto_policy_ref" /></label><label>Salaried time requirement<select className="block w-full" name="salaried_time_requirement" required><option value="required">Required</option><option value="not_required">Not required</option><option value="policy_dependent">Policy dependent</option></select></label>
      <label className="flex items-center gap-2 md:col-span-2"><input name="overtime_enabled" type="checkbox" /> Configure overtime authority in this policy</label><label>Weekly overtime threshold (minutes)<input className="block w-full" name="weekly_threshold_minutes" type="number" min="1" defaultValue="2400" /></label><label>Overtime multiplier<input className="block w-full" name="overtime_multiplier" placeholder="1.5" /></label><label>Workweek start day (0 = Sunday)<input className="block w-full" name="workweek_start_day" type="number" min="0" max="6" defaultValue="0" /></label><label>Workweek start time<input className="block w-full" name="workweek_start_time" placeholder="00:00" /></label>
      <label>Pre-finalization corrections<input className="block w-full" name="pre_finalization_correction_treatment" required /></label><label>Post-finalization adjustments<input className="block w-full" name="post_finalization_adjustment_treatment" required /></label><label>Post-payment adjustments<input className="block w-full" name="post_payment_adjustment_treatment" required /></label><label>Cutoff rule<input className="block w-full" name="cutoff_rule" required /></label><label>Required time approvals<input className="block w-full" name="required_time_approvals" type="number" min="1" defaultValue="1" required /></label><label>Decision evidence reference<input className="block w-full" name="decision_evidence_digest" required /></label><label className="md:col-span-2">Why is this policy being drafted?<textarea className="block w-full" name="audit_reason" required /></label><Button className="md:col-span-2" disabled={actions.draft.isPending} type="submit">Save Payroll policy draft</Button>
    </form>}
    {!canManage && <p className="text-sm text-content-muted">Policy editing requires Payroll policy management authority. An authorized approver can approve a draft without editing it.</p>}
  </CardContent></Card>;
}
