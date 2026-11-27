# All County QBO transaction evidence recovery

Status: **externally blocked before disposition-only admission**

This packet records the bounded search for the November 19 QuickBooks Online
transaction envelopes. It does not reconstruct transactions from reports, call
QuickBooks, create native Accounting records, or change protected financial
state.

## Result

The original transaction-envelope store was created on Beta at
`/var/lib/acp-qbo-production-evidence` by run
`qbo-production-20261119T235000Z`. The acquisition completed at
`2026-11-20T00:32:07.269391+00:00` with 20,702 records and bounded-snapshot
digest `e4d672c1cdfca858e4a8e923a51a86627753c7ea1fedc695daa98066a5dc6041`.

The Docker volume still exists and was created on November 12, before the
acquisition. It has not been recreated. Its current contents do not include the
required `runs/`, `envelopes/`, or `blobs/` trees. Searches of the Beta Docker
volumes, Beta release/backup locations, OM1 custody locations, mounted external
volumes, Laptop Master custody locations, Git objects, branches, and prior
handoffs found no second copy of the envelope store.

The surviving manual archive is intact but is not a substitute. Its custody
manifest lists 21 source files; all 21 independently matched their recorded
size and SHA-256, and all 24 files in the package are mode `0600`. The custody
manifest SHA-256 is
`f6640c0d531eaa8a822e82f697b3aaead65c8ae7b52a3c527e9616642c4d4f4a`.

The expected bounded digest is independently present in both surviving control
documents:

- reconciliation register SHA-256
  `b0e3d11de08e361efc9beeefd8a8509800a9c1ef87337372beee80c00b2e6c40`;
- original no-write rehearsal SHA-256
  `6b99654147f82a7eca5e6296b09dd4aa99256d7eea1099bee3e60aff94325f33`.

This corroborates the acquisition-time digest. It does **not** independently
verify the missing envelope objects. Verification remains blocked until the
original objects are recovered from a host snapshot or a new source snapshot
is acquired and sealed under a new identity.

## Existing connection assessment

The current Beta runtime cannot perform a new acquisition without governed
restoration:

- `QBO_PRODUCTION_ENABLED` is false;
- the current callback configuration is the legacy Preview callback;
- the production runtime root is mode `0755` and fails the protected-store
  permission check;
- the protected client credential file exists at mode `0600`;
- the OAuth token, verified-company marker, and exact company-name binding are
  absent;
- no new OAuth authorization was initiated.

The previous authorized connection is therefore proven unusable in its current
state. Reacquisition requires a governed GET-only Beta release and a new owner
OAuth authorization. Any such acquisition must use a new run ID, timestamp,
manifest, and bounded-snapshot digest. It must never be represented as the
November 19 archive.

## Original source disposition evidence

The surviving acquisition-time rehearsal ran directly against the original
envelope store and failed if it encountered a duplicate source identity. It
reported:

| Disposition population | Count |
|---|---:|
| Exact native bindings | 0 |
| Unresolved Account/Customer/Vendor/Journal mappings | 1,941 |
| Invoice/Payment/Purchase/Deposit/Transfer contract holds | 18,463 |
| Unsupported or separate-authority families | 298 |
| Duplicate source identities | 0 |
| Total held source records | 20,702 |
| Provider-unavailable families | 1 (`tax_payment`) |

The 1,941 unresolved mappings comprise 131 Accounts, 909 Customers, 868
Vendors, and 33 Journal Entries. The 18,463 contract holds comprise 1,341
Invoices, 1,237 Payments, 12,414 Purchases, 3,456 Deposits, and 15 Transfers.
The 298 unsupported records comprise CompanyInfo, Employees, Items, Payment
Methods, Refund Receipts, and Terms.

The prior rehearsal created zero application records and performed zero QBO or
Accounting writes. A new disposition-only database execution was not attempted
without the envelopes; doing so from aggregate reports would destroy exact
provider identity, version, relationship, and provenance controls.

## Finance approval package state

Finance approval is **not ready to issue**. The admission plan and controls are
qualified, but transaction evidence and mappings remain held:

- Chart of Accounts: 131 source Accounts require exact classification and
  native mappings. No opening balance may use a plug.
- Opening balances and General Ledger: the source Trial Balance balances at
  `$2,021,520.50` debit and credit; source Journal lines balance, but native
  opening and GL admission remain held until envelope recovery and per-account
  provenance are complete.
- Invoices: 1,341 records, `$1,939,546.40` total, `$500,584.34` open balance;
  all held for Customer mapping, overlap controls, and the A/R bridge.
- Payments: 1,237 records, `$1,523,656.97` total; 1,171 exact Invoice links are
  preserved. Seventy-three unlinked Payments totaling `$85,414.91` remain
  unapplied holds.
- Customer receivables: source invoice open balances exceed Balance Sheet A/R
  by `$100,801.91`. No balancing transaction or fabricated Payment link is
  authorized.
- Native posting: prohibited. The first executable phase remains disposition
  ledger only after original or newly sealed transaction evidence is present.

## Seven conflicts preserved

1. `D-001`: five General Ledger presentation rows; amount difference `$0.00`.
2. `D-002`: A/R bridge difference `$100,801.91`.
3. `D-003`: 73 unlinked Payments totaling `$85,414.91`; provider unapplied
   `$87,544.91`.
4. `D-004`: 102 unposted American Express rows, including four exact repeats;
   no automatic posting or deduplication.
5. `D-005`: Payroll coverage differences of `$41,734.39` gross and `$35,846.00`
   net.
6. `D-006`: Accounting OAuth scope does not provide detailed Payroll data.
7. `D-007`: source evidence has not been admitted into native structures.

## Exact recovery actions

### Preferred: recover the original store

The owner or authorized infrastructure custodian must inspect DigitalOcean
backups/snapshots for droplet `618323703` (`acp-beta-clean`, `nyc2`) covering
the interval after `2026-11-20T00:32:07Z` and before the evidence disappeared.
Do not restore a snapshot over Beta. Create an isolated recovery droplet or
read-only recovery volume, then copy only the original
`preview_qbo_production_evidence/_data/{runs,envelopes,blobs}` trees through
approved custody. Laptop Master must seal the recovered archive, record its
archive SHA-256 and file manifest, and independently recompute the bounded
snapshot digest. Continue only if it equals the expected digest exactly.

### Fallback: acquire a new source snapshot

If no qualifying host snapshot exists, Laptop Master must obtain a separate
Beta Release GO for the already governed direct-Beta, GET-only QBO runtime,
restore protected directory ownership, provision the exact All County company
binding and verified-company marker, and retain the protected client
credential. The owner must then complete the official Intuit authorization in
a fresh browser session. No worker may complete OAuth for the owner.

After authorization, run the existing bounded production acquisition with the
November 19 accounting cutoff and a new recovery run ID. Seal and transfer the
new `runs/envelopes/blobs` store to Laptop Master, record its distinct digest
and timestamp, and reconcile it to the November 19 counts and financial
controls. Provider drift must be reported, not rewritten. Only then may the
existing disposition-only service run in a disposable database.

Neither path authorizes QBO writes, native posting, bank-feed changes, Payroll,
or protected financial-record mutation.
