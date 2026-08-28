# ECO.MEASUREMENT.PACKAGE.1 — Deterministic readiness package

The measurement readiness package seals one Company/Branch/subject/reconciliation
boundary with its normalized measurement inputs, relevant Economics findings,
versioned policy prerequisites, and deterministic contribution-measurement gate. It is
an immutable replay contract, not a profitability calculation or persistence model.

The package digest binds package and measurement definition versions; Company,
Branch, subject, and reconciliation identities; source authorities and acceptance;
confidence and evidence states; optional source values and units; effective/as-of
context; limitations; evidence/value/source-package digests; complete relevant
findings; policy state; component blockers; and the gate result. The package identity
is derived from that digest.

Sealing replays the gate and rejects an inconsistent result. Verification repeats
scope checks, gate replay, canonicalization, and digest comparison. Changes to an
identity, value digest, authority, acceptance state, finding, policy, blocker, or gate
therefore fail verification or create a different sealed package. Identical canonical
state creates the identical identity and digest.

Company and Branch are now retained on measurement inputs. They are optional while an
input is being composed for backward compatibility, but a readiness package refuses
to seal any input whose scope is absent or different from the package boundary.

Missing values remain unavailable rather than zero. Conflicts remain conflicts. QBO
and public HCP assertions retain their unaccepted authority. Unresolved Finance/owner
policies remain packaged blockers. No revenue recognition, contribution, profit,
margin, leakage amount, allocation, ranking, forecast, price, or remediation is
computed.
