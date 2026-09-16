# Price Book P0 Preview operability

## Incident truth

The owner-observed Preview backend reports release
`a109743968fc764fc1885ecf8fbd4abeb87846d7`. That release predates native All
County candidate admission (`o1q9r27h4u0v`) and activation review
(`p2r0s28i5v1w`). Code presence, schema presence, candidate admission, and UI
operability are separate gates. A deployment alone does not populate the
catalog.

The public health contract does not expose tenant data or the database Alembic
revision. Release must collect schema and counts through the sanctioned Preview
host/database boundary; workers must not infer them from an empty screen.

## Enterprise Release execution

1. Deploy the current protected release through the normal Preview pipeline.
   Do not deploy this worker branch directly.
2. Back up Preview PostgreSQL and run the normal migration service. Verify one
   head and `current=head`.
3. Before admission, record Company-scoped native and candidate counts using a
   read-only database session. Never print Customer, price, or credential data.
4. From the deployed release `backend/` directory, run exactly:

   ```text
   python -m scripts.pricebook_candidate_admission \
     --configuration ../docs/architecture/price-book/all-county-build-1.configuration.json \
     --readiness ../docs/architecture/price-book/all-county-activation-readiness-1.json \
     --company-id <ALL_COUNTY_COMPANY_ID> \
     --actor-user-id <AUTHORIZED_ALL_COUNTY_OWNER_USER_ID> \
     --idempotency-key all-county-build-1-admission-v1
   ```

5. Preserve the emitted admission run, packet digest, and result counts. Run the
   identical command once more. The second result must identify the same run and
   create no category, service, version, binding, or audit duplicate.
6. Verify, without forcing expected values: category totals/statuses; service
   totals/statuses; active price versions; service/category bindings; admitted
   and held candidate bindings; and source/evidence digests. The qualified packet
   expectation is 16 draft categories, 179 draft services, 39 held services,
   and zero active candidate prices.
7. Sign in as an authorized All County owner and search `drain`, `sewer`,
   `toilet`, and `water heater`, plus one exact service code and one category
   name. Open a draft service, verify category/source/readiness/candidate price,
   return to results, and repeat. Confirm held Water Heater evidence explains the
   unresolved source conflict.
8. Confirm the Estimate selector can read eligible native service authority.
   Do not create a sold snapshot merely for this deployment check.

The admission implementation creates draft Price Book authority and provenance
bindings only. It does not activate a price, map or create Inventory, infer tax
policy, or turn expected material into purchased or consumed material.
