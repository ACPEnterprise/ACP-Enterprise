# OM2 QuickBooks report readback

Assignment `OM2-QBO-REPORT-READBACK-02` is qualified from completed synthetic
checkpoint `6793f16d3f6b20ed62ec12dca0626927b695b8be` under authoritative queue
checkpoint `67bbd83d874f33e4926c530968d5c35e9940a7ba`.

The source-backed accounting history projection now supports deterministic,
read-only report evidence. It preserves report kind and source ID, date range,
basis, currency, exact account relationships, source-reported total,
relationship total, evidence digest, and every exception. Missing or held
account relationships, conflicting report evidence, and total disagreement
remain explicit held dispositions; no balancing value or posting is invented.

Qualification uses synthetic accounts and reports only. It is not protected
QBO custody, OAuth, All County financial acceptance, native admission,
financial posting, or browser acceptance. QuickBooks remains authoritative.
