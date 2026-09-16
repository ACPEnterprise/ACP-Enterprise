# All County Price Book candidate admission

This release admits the sealed `all-county-build-1` configuration into native
ACP draft authority. It never activates a price and never creates or maps an
Inventory item.

## Protected integration and execution

1. Merge the candidate only after its migration rebases cleanly on the current
   protected Alembic head.
2. Run a fresh zero-to-head migration and verify `alembic current` equals the
   sole `alembic heads` result.
3. Execute from `backend/` with the Preview database configuration and an
   existing authorized All County owner identity:

   ```text
   python -m scripts.pricebook_candidate_admission \
     --configuration ../docs/architecture/price-book/all-county-build-1.configuration.json \
     --readiness ../docs/architecture/price-book/all-county-activation-readiness-1.json \
     --company-id <ALL_COUNTY_COMPANY_ID> \
     --actor-user-id <AUTHORIZED_OWNER_USER_ID> \
     --idempotency-key all-county-build-1-admission-v1
   ```

4. Preserve and compare the printed packet digest. Repeat the exact command to
   prove replay returns the same admission run with no additional rows/audits.
5. Verify native totals: 16 draft categories, 179 draft services, 39 held
   service candidates, and zero active candidate price versions.
6. In Price Book, search `drain`, `water heater`, `toilet`, and `sewer` and
   confirm source, candidate price, review requirements, and held conflicts.

Any changed packet under `all-county-pricebook-candidate-v1` fails closed. A
genuine source update requires an explicit successor configuration version.

## Bounded first activation review (activation is not authorized here)

| Candidate | Proposed reason | Remaining prerequisites |
| --- | --- | --- |
| SVC-001 | Standard diagnostic visit | Owner price approval; accountant tax-class decision; effective date |
| SVC-002 | After-hours service call | Owner price/after-hours-policy approval; accountant tax-class decision; effective date |
| DRN-001 | Single-toilet auger | Owner price approval; accountant tax-class decision; material mapping only if canonical activation policy later requires it; effective date |
| DRN-002 | Bath/shower drain cable | Owner price approval; accountant tax-class decision; material mapping only if canonical activation policy later requires it; effective date |

Water Heater candidates are excluded from this first cohort because their
workbook prices conflict with illustrative script examples. Owner review must
resolve source precedence before any such item can proceed.

Rollback before admission is the schema downgrade. After admission, do not
delete evidence casually: preserve the append-only audit and candidate
bindings and use a governed successor/disposition workflow.
