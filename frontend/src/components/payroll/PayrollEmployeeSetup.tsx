import { useState, type FormEvent } from "react";
import { useHasPermission } from "../../auth";
import { usePayrollEmployeeSetup } from "../../hooks/usePayroll";
import { draftPayrollInput } from "../../api/payroll";
import { Alert, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Spinner } from "../../ui";

const label = (value: string) => value.replaceAll("_", " ").replaceAll(":", " · ");
const taxKeys = ["w4_filing_status","w4_step_2","w4_step_3","w4_step_4a","w4_step_4b","w4_step_4c","work_jurisdiction","residence_jurisdiction","state_local_withholding_configuration","unemployment_workforce_jurisdiction","social_security_applicability","social_security_wages_ytd","social_security_tax_ytd","medicare_applicability","medicare_wages_ytd","medicare_tax_ytd","additional_medicare_prerequisites","federal_withholding_ytd","prior_payroll_coverage","federal_tax_table","state_local_tax_table","tax_table_source_version","tax_table_effective_date"];
const deductionKeys = ["deduction_configuration","deduction_tax_treatment","deduction_effective_date","deduction_limits"];

export function PayrollEmployeeSetup({ employeeId }: { employeeId: string }) {
  const canReadCompensation = useHasPermission("COMPANY_PAYROLL_COMPENSATION_READ");
  const canReadTax = useHasPermission("COMPANY_PAYROLL_TAX_AUTHORITY_READ");
  const canReadDeduction = useHasPermission("COMPANY_PAYROLL_DEDUCTION_AUTHORITY_READ");
  const canRead = canReadCompensation || canReadTax || canReadDeduction;
  const canComp = useHasPermission("COMPANY_PAYROLL_COMPENSATION_MANAGE");
  const canTax = useHasPermission("COMPANY_PAYROLL_TAX_AUTHORITY_MANAGE");
  const canDeduction = useHasPermission("COMPANY_PAYROLL_DEDUCTION_AUTHORITY_MANAGE");
  const canApproveCompensation = useHasPermission("COMPANY_PAYROLL_COMPENSATION_APPROVE");
  const canApproveTax = useHasPermission("COMPANY_PAYROLL_TAX_AUTHORITY_APPROVE");
  const canApproveDeduction = useHasPermission("COMPANY_PAYROLL_DEDUCTION_AUTHORITY_APPROVE");
  const canApproveInput = canApproveTax || canApproveDeduction;
  const setup = usePayrollEmployeeSetup(employeeId, canRead);
  const [message, setMessage] = useState("");
  if (!canRead) return <Alert variant="warning">Payroll setup requires compensation or tax/deduction read authority.</Alert>;
  if (setup.query.isPending) return <Spinner label="Loading Employee Payroll setup" />;
  if (setup.query.isError || !setup.query.data) return <Alert variant="danger">Employee Payroll setup is unavailable. No value was changed.</Alert>;
  const value = setup.query.data;
  const submitCompensation = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setMessage(""); const data = new FormData(event.currentTarget);
    const type = String(data.get("compensation_type")) as "hourly" | "salaried";
    try {
      await setup.draftCompensation.mutateAsync({ effective_start: String(data.get("effective_start")), compensation_type: type, hourly_rate: type === "hourly" ? String(data.get("amount")) : null, salary_amount: type === "salaried" ? String(data.get("amount")) : null, salary_frequency: type === "salaried" ? String(data.get("salary_frequency")) : null, worker_class_reference: String(data.get("worker_class_reference") || "") || null, audit_reason: String(data.get("audit_reason")) });
      setMessage("Compensation draft saved. A different authorized approver must approve it."); event.currentTarget.reset();
    } catch { setMessage("Compensation draft was not saved. Review the effective date, amount, permissions, and overlap history."); }
  };
  const submitInput = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setMessage(""); const data = new FormData(event.currentTarget);
    const key = String(data.get("authority_key")); const domain = deductionKeys.includes(key) ? "deduction" : "tax";
    const protectedValue = String(data.get("protected_value") || "");
    try {
      await draftPayrollInput(employeeId, { domain, authority_key: key, applicability: String(data.get("applicability")) as "required" | "not_applicable", effective_start: String(data.get("effective_start")), jurisdiction_reference: String(data.get("jurisdiction_reference") || "") || null, calculation_basis: String(data.get("calculation_basis") || "") || null, priority: domain === "deduction" ? Number(data.get("priority") || 0) : null, public_parameters: {}, protected_values: protectedValue ? { value: protectedValue } : null, audit_reason: String(data.get("audit_reason")) });
      await setup.query.refetch();
      setMessage("Payroll input draft saved. A different authorized approver must approve it."); event.currentTarget.reset();
    } catch { setMessage("Payroll input was not saved. Protected-input encryption, permissions, or effective-date authority may be unavailable."); }
  };
  return <Card>
    <CardHeader><CardTitle>Employee Payroll setup · {value.employee_name}</CardTitle><CardDescription>{value.employee_number} · effective-dated, audit-preserving authority</CardDescription></CardHeader>
    <CardContent className="space-y-6">
      <Alert variant={value.readiness === "READY_FOR_PAYROLL" ? "success" : "warning"} title={value.readiness}>
        {value.blockers.length ? <ul className="list-disc pl-5">{value.blockers.map((item) => <li key={item}>{label(item)}</li>)}</ul> : "All currently admitted Payroll requirements are ready."}
      </Alert>
      {message && <Alert variant="information">{message}</Alert>}
      {!value.protected_input_configuration_ready && <Alert variant="warning" title="Protected Payroll input storage unavailable">W-4 and other confidential values cannot be saved until Enterprise configures the Payroll input encryption keyring. Existing evidence remains unchanged.</Alert>}
      <section><h3 className="font-semibold">Compensation history</h3>{value.compensations.length ? <ul>{value.compensations.map((item) => <li key={item.id}>Version {item.version} · {label(item.lifecycle)} · {String(item.effective_start)} · {label(String(item.compensation_type))}{item.lifecycle === "draft" && canApproveCompensation ? <Button className="ml-2" type="button" onClick={() => setup.approveCompensation.mutate(item.id)}>Approve</Button> : null}</li>)}</ul> : <p className="text-content-muted">No compensation authority. Missing compensation is not zero.</p>}</section>
      {canComp && <form className="grid gap-3 rounded-lg border border-stroke p-4 md:grid-cols-2" onSubmit={submitCompensation}>
        <h3 className="md:col-span-2 font-semibold">Add effective-dated compensation</h3>
        <label>Pay basis<select name="compensation_type" className="block w-full" required><option value="hourly">Hourly</option><option value="salaried">Salary</option></select></label>
        <label>Rate or salary amount<input name="amount" type="number" min="0.0001" step="0.0001" className="block w-full" required /></label>
        <label>Effective date<input name="effective_start" type="date" className="block w-full" required /></label>
        <label>Salary frequency<select name="salary_frequency" className="block w-full"><option value="weekly">Weekly</option><option value="annual">Annual</option></select></label>
        <label>Worker classification reference<input name="worker_class_reference" className="block w-full" /></label>
        <label>Reason<input name="audit_reason" className="block w-full" required /></label>
        <Button type="submit">Save compensation draft</Button>
      </form>}
      <section><h3 className="font-semibold">Tax and deduction authority history</h3>{value.inputs.length ? <ul className="space-y-1">{value.inputs.map((item) => <li key={item.id}>{label(item.domain)} · {label(item.key)} · version {item.version} · {label(item.lifecycle)}{item.lifecycle === "draft" && canApproveInput ? <Button className="ml-2" type="button" onClick={() => setup.approveInput.mutate(item.id)}>Approve</Button> : null}</li>)}</ul> : <p className="text-content-muted">No tax or deduction authority is configured. Missing inputs are not zero.</p>}</section>
      {(canTax || canDeduction) && <form className="grid gap-3 rounded-lg border border-stroke p-4 md:grid-cols-2" onSubmit={submitInput}>
        <h3 className="md:col-span-2 font-semibold">Add effective-dated Payroll input</h3>
        <label>Exact missing input<select name="authority_key" className="block w-full" required>{[...(canTax ? taxKeys : []), ...(canDeduction ? deductionKeys : [])].map((key) => <option key={key} value={key}>{label(key)}</option>)}</select></label>
        <label>Applicability<select name="applicability" className="block w-full"><option value="required">Required / supplied</option><option value="not_applicable">Approved not applicable</option></select></label>
        <label>Effective date<input name="effective_start" type="date" className="block w-full" required /></label>
        <label>Jurisdiction reference<input name="jurisdiction_reference" className="block w-full" /></label>
        <label>Calculation basis<input name="calculation_basis" className="block w-full" placeholder="Existing rule/provider reference" /></label>
        <label>Deduction priority<input name="priority" type="number" min="0" className="block w-full" /></label>
        <label className="md:col-span-2">Confidential value for this exact input<input name="protected_value" type="password" autoComplete="off" className="block w-full" /><span className="text-xs text-content-muted">Enter filing status, Step value, YTD amount, deduction configuration, or rule reference required by the selected blocker. The value is write-only.</span></label>
        <label>Reason<input name="audit_reason" className="block w-full" required /></label>
        <Button type="submit">Save Payroll input draft</Button>
      </form>}
      <p className="text-xs text-content-muted">Saving setup does not calculate Payroll, change a prior period, transmit wages, file tax, move money, or post Accounting.</p>
    </CardContent>
  </Card>;
}
