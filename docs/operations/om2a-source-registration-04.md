# OM2-A protected source registration

Synthetic qualification adds a tenant-bound, checksum-verified registration
contract for sealed HCP/QBO manifests. Registrations retain provider, source
digest, manifest digest, acquisition provenance, and object count while
remaining read-only and not admitted as native data.

Missing, changed, cross-tenant, or non-GET-only evidence fails closed. No
protected manifest was available and no live registration or provider write was
performed.
