# OM2 reconciliation exception readback

Assignment `OM2-RECONCILIATION-EXCEPTIONS-02` adds a deterministic,
tenant/Branch-scoped administrator readback for ambiguous identities, missing
parents, and source-version conflicts. Every row preserves its source key,
related source keys, explanation, and evidence digest.

The only available dispositions are evidence review and keeping the item held.
Automatic merge is explicitly disabled. Qualification is synthetic and makes
no database or live-data mutation.
