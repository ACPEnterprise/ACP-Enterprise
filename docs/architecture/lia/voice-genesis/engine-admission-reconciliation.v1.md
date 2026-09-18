# Voice Genesis to speech-engine admission reconciliation v1

The canonical rights and source authority remains `app.lia.voice_genesis`.
`app.twelve_hats_speech` does not create, approve, repair, or infer rights. Its
adapter accepts only a reproducible `DatasetManifest` plus the exact complete
set of admitted `RightsLedgerAsset` records named by that manifest.

Training eligibility requires exact agreement on asset identity, source-file
digest, transcript digest, dataset version, rights approval, technical quality,
and admission state. Missing, extra, duplicate, cross-version, revoked,
quarantined, or contradictory evidence fails closed. Rights evidence is sorted
by asset identity before canonical hashing, making equivalent custody packets
order-independent.

The adapter returns `SpeechDatasetVersion` only after this reconciliation. That
projection can then pass the existing training-run admission checks; it grants
no new rights and starts no training. The admission timestamp must be explicit
and timezone-aware because the current Genesis manifest does not manufacture a
timestamp.

There is currently no admitted dataset, model, training run, acoustic result,
inference service, external provider, credential, or deployment.
