# OM2 HCP job relationship reconciliation

Assignment `OM2-HCP-JOB-RELATIONSHIP-02` is qualified with synthetic records
only. The authoritative queue checkpoint is
`67bbd83d874f33e4926c530968d5c35e9940a7ba`; the source implementation
checkpoint is `6c999f50876a227e27488f347e56848250e23264`.

The read-only reconciliation contract now requires every projected HCP job to
retain both its explicit customer and location parents. Appointments,
estimates, and invoices require a job parent; payments require an invoice
parent. Existing-but-wrong parent namespaces are held separately from missing
parents, and an exception at any parent prevents projection of every dependent
descendant. No relationship, lifecycle state, or source value is inferred.

Qualification uses sanitized in-memory fixtures and exercises valid graph
replay, missing parents, invalid relationship shapes, conflicting source
evidence, and transitive held-exception propagation. This is isolated
engineering evidence, not protected-source custody, All County population
acceptance, native admission, HCP connectivity, or browser acceptance. The
path performs no provider or database writes.
