# Finance real-world operating experience 2

## Authority and boundary

This candidate starts from protected authority `bae55401586e48e4b606604c3aac1eeef4832a27`
and is reconciled onto the current protected successor before handoff. It composes
the existing sealed QuickBooks source-evidence and source-backed report contracts;
it does not post ACP ledger entries, call a QuickBooks write API, execute a payment,
or promote source evidence to ACP-native Accounting.

PR #305 and its May 2026 source-backed Profit and Loss implementation are unchanged.
This candidate supplies the surrounding daily owner experience.

## Owner experience

- QuickBooks Source Center separates connection, acquisition, reconciliation, and
  ACP-native authority.
- The report catalog explains what is available, partial, or unavailable and why.
- Sealed report history remains inspectable without another provider request.
- Profit and Loss supports explicit cash/accrual basis, custom dates, common period
  shortcuts, CSV export, and printing.
- The account explorer supports name, number, type, and subtype search/filtering.
- General Ledger evidence is filtered by period on the server and returned in pages
  of at most 100 rows, with digest-verified sealed-source authority.
- Existing invoice, bill, and payment evidence retains its explicit QBO-source label.
- Readiness and reconciliation limitations are translated into owner-action language.

## Integration qualification

Run from the repository root with the supported backend environment:

```bash
PYTHONPATH=backend pytest -q \
  backend/tests/qbo_source/test_accounting_evidence_projection.py \
  backend/tests/qbo_source/test_source_report.py \
  backend/tests/qbo_source/test_intuit_adapter.py \
  backend/tests/qbo_source/test_control_report_projection.py
ruff check backend/app/qbo_source backend/tests/qbo_source
python -m compileall -q backend/app/qbo_source
git diff --check
```

Run from `frontend/`:

```bash
npm run test:run -- \
  src/api/qboAccountingEvidence.test.ts \
  src/components/accounting/QboSourceEvidence.test.tsx \
  src/routes/FinancialReportsRoute.test.tsx
npm run build
npm run lint -- --quiet
```

## Preview acceptance

1. Open **Financial Reports** and confirm the Source Center names the All County
   production realm without exposing a provider credential.
2. Confirm connection, acquisition, reconciliation, and ACP-native states are shown
   independently.
3. Search and filter the account explorer.
4. Select Profit and Loss, May 1–31 2026, and the required basis; generate the report.
5. Confirm actual rows and totals, QBO source-backed authority, realm, source as-of,
   acquisition time, and the statement that it is not yet ACP-native Accounting.
6. Change basis and period and confirm neither is silently substituted when evidence
   is unavailable.
7. Open General Ledger evidence, page through results, and confirm source authority.
8. Inspect invoice and payment evidence and its QBO-source boundary.
9. Inspect readiness explanations and report history.
10. Repeat the core flow at a narrow phone viewport; export CSV and open print view.

Unavailable controls must remain unavailable rather than displaying inferred zeroes.
Balance Sheet, Trial Balance, A/P, customer/vendor balances, or other reports only
become available when their sealed source controls or ACP-native ledger authority
exist.
