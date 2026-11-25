# OM2 historical detail readback

Assignment `OM2-HISTORY-DETAIL-READBACK-03` is based on authoritative queue
`7c7f5c82157fb44ad9a93b6bf1421ea229eb8d57` and uses synthetic fixtures only.

Historical Customer results now expose actual source-backed Location, Job,
Appointment, Estimate, Invoice, Payment, and Refund detail rather than counts
alone. Each record retains its provider source identity. Missing Job-to-Location
or Appointment/Invoice-to-Job relationships render as explicit held
relationships, never inferred links. HCP/QBO overlap dispositions and unsafe
refund aggregation remain visible.

The browser surface remains read-only and identifies the sealed manifest. No
native Customer overwrite, live admission, provider write, accounting posting,
or All County protected-data acceptance is claimed.
