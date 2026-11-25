# OM2 historical customer UI reconciliation

Assignment `OM2-CUSTOMER-HISTORY-UI-RECON-02` is implemented from synthetic
checkpoint `6c999f50876a227e27488f347e56848250e23264` under authoritative queue
checkpoint `67bbd83d874f33e4926c530968d5c35e9940a7ba`.

The existing Customers screen now includes a separate historical-only search
over the sealed, GET-only HCP source package. Search accepts source ID, name,
contact value, and location text without requiring a native Customer identity.
An authorized operator can open the source-backed journey and see preserved
location and downstream domain counts. The UI labels the result historical
only, exposes no mutation action, and does not silently substitute the native
Customer roster.

Backend qualification uses synthetic sealed-package fixtures. Component
acceptance verifies search, historical/source-backed labeling, journey
readback, location visibility, and absence of edit/admit/import/create actions.
This is isolated browser-contract acceptance, not protected custody, live data,
native admission, provider connectivity, or actual All County acceptance.
