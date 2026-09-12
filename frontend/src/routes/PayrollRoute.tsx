import { useState } from "react";
import { useHasPermission } from "../auth";
import { Link, useSearchParams } from "react-router";

import { useComplianceSchemas, usePayrollOperatingRegisters, usePayrollOperationsSummary, usePayrollPeriodOperations, usePayrollReports } from "../hooks/usePayroll";
import { useCurrentPayPeriod, usePayPeriods } from "../hooks/useWorkdayTime";
import { Alert, Card, CardContent, CardDescription, CardHeader, CardTitle, Spinner } from "../ui";
import { PayrollEmployeeSetup } from "../components/payroll/PayrollEmployeeSetup";

const label = (value: string) => value.replaceAll("_", " ").replaceAll(":", " · ");

function StateList({ values, empty }: { values: Record<string, number>; empty: string }) {
  const entries = Object.entries(values).sort(([left], [right]) => left.localeCompare(right));
  if (!entries.length) return <p className="text-sm text-content-muted">{empty}</p>;
  return (
    <dl className="grid gap-2">
      {entries.map(([state, count]) => (
        <div className="flex justify-between gap-4 border-b border-stroke py-2" key={state}>
          <dt className="capitalize">{label(state)}</dt>
          <dd className="font-semibold tabular-nums">{count}</dd>
        </div>
      ))}
    </dl>
  );
}

export function PayrollRoute() {
  const [searchParams] = useSearchParams();
  const setupEmployeeId = searchParams.get("employee");
  const canReadReporting = useHasPermission("COMPANY_PAYROLL_REPORTING_READ");
  const canRead = canReadReporting;
  const operations = usePayrollOperationsSummary(canRead);
  const reports = usePayrollReports(canRead);
  const schemas = useComplianceSchemas(canRead);
  const canReadTime = useHasPermission("COMPANY_TIMEKEEPING_ADMIN_READ");
  const currentPeriod = useCurrentPayPeriod(canRead && canReadTime);
  const payPeriods = usePayPeriods(canRead && canReadTime);
  const [selectedPayPeriodId, setSelectedPayPeriodId] = useState("");
  const effectivePayPeriodId = selectedPayPeriodId || currentPeriod.data?.id || payPeriods.data?.[0]?.id || null;
  const periodOperations = usePayrollPeriodOperations(effectivePayPeriodId, canRead && canReadTime);
  const registers = usePayrollOperatingRegisters(canRead);
  if (!canRead) return <Alert variant="danger">You are not authorized to view Payroll Administration.</Alert>;
  if (operations.isPending || reports.isPending || schemas.isPending || registers.isPending) return <Spinner label="Loading Payroll Administration" />;
  if (operations.isError || reports.isError || schemas.isError || registers.isError || !operations.data)
    return (
      <Alert variant="danger" title="Payroll Administration unavailable">
        Authoritative Payroll readiness could not be loaded. No Payroll action was taken.
      </Alert>
    );
  const value = operations.data;
  const approvedRunCount = value.run_counts.approved ?? 0;
  return (
    <div className="mx-auto max-w-7xl space-y-6 pb-12">
      <header>
        <p className="text-sm font-semibold text-action-primary">Financial Operations</p>
        <h1 className="mt-1 text-2xl font-bold sm:text-3xl">Payroll Administration</h1>
        <p className="mt-2 text-content-muted">Readiness, reconciliation, reporting, payment, remittance, statements, and correction evidence. Provider execution and filing remain disabled.</p>
      </header>
      {setupEmployeeId && <PayrollEmployeeSetup employeeId={setupEmployeeId} />}
      <Alert variant={value.blocker_count ? "warning" : "information"} title={value.blocker_count ? "Payroll attention required" : "Payroll evidence reconciled"}>
        {value.blocker_count ? `${value.blocker_count} Employee disposition blocker(s) remain explicit.` : "No unexplained Employee blocker is present in the admitted run population."} History: {value.history_ready ? "complete authority available" : "incomplete—YTD remains unavailable"}.
      </Alert>
      <Card>
        <CardHeader>
          <CardTitle>Current pay-period review</CardTitle>
          <CardDescription>Accepted time through compensation, withholding, and gross-pay readiness. This view does not calculate or transmit Payroll.</CardDescription>
        </CardHeader>
        <CardContent>
          {!canReadTime && (
            <Alert variant="warning" title="Time evidence permission required">
              Payroll reporting is available, but detailed Employee time requires Timekeeping Administration read authority.
            </Alert>
          )}
          {canReadTime && currentPeriod.isLoading && <Spinner label="Loading current pay period" />}
          {canReadTime && currentPeriod.isError && (
            <Alert variant="danger" title="Pay period unavailable">
              No Payroll value was inferred or changed.
            </Alert>
          )}
          {canReadTime && currentPeriod.data === null && (
            <Alert variant="warning" title="No current pay period">
              Configure authoritative pay-period dates before office review.
            </Alert>
          )}
          {periodOperations.isLoading && <Spinner label="Loading Payroll period readiness" />}
          {periodOperations.isError && (
            <Alert variant="danger" title="Payroll period readiness unavailable">
              Supporting evidence could not be composed safely. No Payroll action was taken.
            </Alert>
          )}
          {periodOperations.data && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label className="font-semibold">
                  Pay period
                  <select aria-label="Payroll pay period" className="ml-2 min-h-10 rounded-lg border border-stroke bg-surface px-2 font-normal" value={effectivePayPeriodId ?? ""} onChange={(event) => setSelectedPayPeriodId(event.target.value)}>
                    {(payPeriods.data ?? []).map((period) => (
                      <option key={period.id} value={period.id}>
                        {period.period_start} – {period.period_end}
                      </option>
                    ))}
                  </select>
                </label>
                <span className="text-sm">
                  Payroll policy: <strong>{label(periodOperations.data.policy_readiness)}</strong>
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1050px] text-left text-sm">
                  <thead>
                    <tr className="text-content-muted">
                      <th className="pb-2">Employee</th>
                      <th>Accepted hours</th>
                      <th>Regular-rate candidate</th>
                      <th>Overtime premium candidate</th>
                      <th>Compensation</th>
                      <th>Withholding</th>
                      <th>Gross pay</th>
                      <th>Review</th>
                      <th>Exceptions</th>
                      <th>Evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {periodOperations.data.employees.map((employee) => (
                      <tr className="border-t border-stroke align-top" key={employee.employee_id}>
                        <td className="py-3">
                          <strong>{employee.display_name}</strong>
                          <p className="text-xs text-content-muted">{employee.employee_number}</p>
                        </td>
                        <td>{(employee.accepted_minutes / 60).toFixed(2)}</td>
                        <td>{employee.regular_candidate_minutes === null ? "Not calculated" : (employee.regular_candidate_minutes / 60).toFixed(2)}</td>
                        <td>{employee.overtime_candidate_minutes === null ? "Not calculated" : (employee.overtime_candidate_minutes / 60).toFixed(2)}</td>
                        <td>{label(employee.compensation_readiness)}</td>
                        <td>{label(employee.withholding_readiness)}</td>
                        <td>{label(employee.gross_pay_readiness)}</td>
                        <td>{label(employee.payroll_review_status)}</td>
                        <td>
                          {employee.exception_codes.length ? (
                            <ul className="space-y-1">
                              {employee.exception_codes.map((item) => (
                                <li key={item}>{label(item)}</li>
                              ))}
                            </ul>
                          ) : (
                            "None"
                          )}
                        </td>
                        <td>
                          <Link className="font-semibold text-action-primary underline" to={`/workforce?employee=${employee.employee_id}#timecard-${employee.employee_id}`}>
                            View timecard
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-content-muted">Regular-rate and overtime-premium candidates appear only after the accepted Payroll engine persists them. Missing configuration is never treated as zero.</p>
            </div>
          )}
        </CardContent>
      </Card>
      <section aria-label="Payroll readiness" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>Approved gross</CardTitle>
            <CardDescription>Accepted Payroll runs only</CardDescription>
          </CardHeader>
          <CardContent className="text-2xl font-bold tabular-nums">{approvedRunCount ? value.aggregate_approved_gross : "Unavailable"}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Approved net</CardTitle>
            <CardDescription>Before payment execution</CardDescription>
          </CardHeader>
          <CardContent className="text-2xl font-bold tabular-nums">{approvedRunCount ? value.aggregate_approved_net : "Unavailable"}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Reconciliation</CardTitle>
            <CardDescription>All known dispositions</CardDescription>
          </CardHeader>
          <CardContent className="capitalize">{label(value.reconciliation_state)}</CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Provider boundary</CardTitle>
            <CardDescription>No provider selected</CardDescription>
          </CardHeader>
          <CardContent className="text-sm capitalize">
            Filing · {label(value.provider_readiness.filing)}
            <br />
            Payment · {label(value.provider_readiness.payment)}
            <br />
            Remittance · {label(value.provider_readiness.remittance)}
          </CardContent>
        </Card>
      </section>
      <section className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Payroll runs</CardTitle>
            <CardDescription>Assembly, review, and final approval</CardDescription>
          </CardHeader>
          <CardContent>
            <StateList values={value.run_counts} empty="No synthetic or operational runs." />
            <h3 className="mt-5 font-semibold">Employee dispositions</h3>
            <StateList values={value.member_dispositions} empty="No run population assembled." />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Payments</CardTitle>
            <CardDescription>Release and settlement evidence</CardDescription>
          </CardHeader>
          <CardContent>
            <StateList values={value.payment_counts} empty="No payment authority prepared." />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Remittance</CardTitle>
            <CardDescription>Tax, deduction, and benefit obligations</CardDescription>
          </CardHeader>
          <CardContent>
            <StateList values={value.remittance_counts} empty="No remittance obligations identified." />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Reporting & compliance</CardTitle>
            <CardDescription>Period, quarter, annual, and prepared packages</CardDescription>
          </CardHeader>
          <CardContent>
            <StateList values={value.reporting_counts} empty="No reporting snapshot prepared." />
            <p className="mt-4 text-sm">
              Configured schemas: <strong>{schemas.data?.length ?? 0}</strong>
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Pay statements</CardTitle>
            <CardDescription>Issued history and protected artifacts</CardDescription>
          </CardHeader>
          <CardContent>
            <StateList values={value.statement_counts} empty="No statement issued." />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Adjustments</CardTitle>
            <CardDescription>Correction and off-cycle authority</CardDescription>
          </CardHeader>
          <CardContent>
            <StateList values={value.adjustment_counts} empty="No open adjustment authority." />
          </CardContent>
        </Card>
      </section>
      <Card>
        <CardHeader>
          <CardTitle>Operating payroll register</CardTitle>
          <CardDescription>Accepted evidence and exact blockers. Approval does not move money, file taxes, or post Accounting.</CardDescription>
        </CardHeader>
        <CardContent>
          {registers.data?.length ? (
            <div className="space-y-5">
              {registers.data.map((register) => {
                const hasCalculatedMember = register.members.some((member) => member.calculation_digest != null);
                return (
                  <section key={register.run_id} className="space-y-3">
                    <h3 className="font-semibold">
                      {register.period_start} – {register.period_end} · {label(register.lifecycle)} / {label(register.review_state)}
                    </h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left">
                            <th>Employee</th>
                            <th>Accepted</th>
                            <th>Regular / OT</th>
                            <th>Gross</th>
                            <th>Withholding</th>
                            <th>Deductions</th>
                            <th>Net</th>
                            <th>Employer liability</th>
                            <th>Status / exceptions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {register.members.map((member) => (
                            <tr className="border-b border-stroke" key={member.employee_id}>
                              <td className="py-3">
                                {member.employee_name}
                                <br />
                                <span className="text-content-muted">{member.employee_number}</span>
                              </td>
                              <td>{member.accepted_minutes === null ? "Unavailable" : `${member.accepted_minutes / 60} h`}</td>
                              <td>{member.regular_minutes === null ? "Unavailable" : `${member.regular_minutes / 60} / ${(member.overtime_minutes ?? 0) / 60} h`}</td>
                              <td>{member.gross ?? "Unavailable"}</td>
                              <td>{member.employee_taxes ?? "Unavailable"}</td>
                              <td>{member.deductions ?? "Unavailable"}</td>
                              <td>{member.net_pay ?? "Unavailable"}</td>
                              <td>{member.employer_liabilities ?? "Unavailable"}</td>
                              <td>
                                {label(member.status)}
                                {member.blockers.length ? (
                                  <ul>
                                    {member.blockers.map((blocker) => (
                                      <li key={blocker}>{label(blocker)}</li>
                                    ))}
                                  </ul>
                                ) : null}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p className="text-sm text-content-muted">
                      {hasCalculatedMember ? (
                        <>
                          Period liabilities: employee withholding {register.liability_totals.employee_taxes} · deductions {register.liability_totals.employee_deductions} · employer liabilities {register.liability_totals.employer_liabilities}.
                        </>
                      ) : (
                        <>Period liabilities unavailable until at least one Employee has an admitted calculation.</>
                      )}{" "}
                      Manual filing/payment required.
                    </p>
                  </section>
                );
              })}
            </div>
          ) : (
            <p className="text-content-muted">No operating Payroll register has been assembled. Missing real Employee inputs remain unaccepted—not zero.</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Reporting history</CardTitle>
          <CardDescription>Authoritative totals remain permission-protected; incomplete history is never presented as YTD.</CardDescription>
        </CardHeader>
        <CardContent>
          {reports.data?.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th>Period</th>
                    <th>Scope</th>
                    <th>State</th>
                    <th>Blockers</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.data.map((report) => (
                    <tr className="border-b border-stroke" key={report.id}>
                      <td className="py-3">
                        {report.period_start} – {report.period_end}
                      </td>
                      <td className="capitalize">{label(report.period_kind)}</td>
                      <td className="capitalize">{label(report.state)}</td>
                      <td>{report.blockers.length ? report.blockers.map(label).join(", ") : "None"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-content-muted">No Payroll reports have been admitted.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
