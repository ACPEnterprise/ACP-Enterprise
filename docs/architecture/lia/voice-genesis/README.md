# LIA Voice Genesis Corpus + Rights v1

This package is the pre-recording authority for the Twelve Hats-owned LIA voice.
It contains no audio, speaker embedding, trained model, contract, credential, or
external-provider dependency.

## Authorities

- `lia-voice-identity.v1.json` and `.md` define LIA's distinct synthetic identity.
- `recording-corpus.v1.json` contains 64 original fictional/non-PII prompts in
  eight recording blocks. Block defaults expand into the complete item contract:
  ID, text, category, delivery, difficulty, important tokens, response mode,
  required material values, and prohibited distortions.
- `rights-lineage.v1.schema.json` defines per-asset rights and provenance.
- `admission-policy.v1.json` makes rights plus technical quality mandatory.
- `recording-session.v1.schema.json` is application-independent session lineage.
- `technical-quality-gates.v1.json` separates objective gates from thresholds
  that require empirical calibration.
- `dataset-manifest.v1.schema.json` plus `app.lia.voice_genesis.dataset_digest`
  make dataset identity deterministic and traceable.
- `privacy-storage-boundary.v1.md` separates source, normalized, transcript,
  rights, manifest, and model-artifact custody.

## Fail-closed flow

```text
PROPOSED
  -> RIGHTS_PENDING
  -> QUALITY_PENDING
  -> ADMITTED

Any unresolved or failed gate
  -> QUARANTINED | REJECTED | REVOKED
```

`ADMITTED` requires explicit approved rights, exclusive Twelve Hats status, all
enumerated training/derivative/commercial/perpetual rights, passed technical
quality, and valid source/transcript digests. Reference measurement never grants
training admission.

## Recording decisions still required

Before recording, the owner must approve the contributor/rights instrument,
recording operator and controlled location, microphone chain, storage custody,
and initial session schedule. Acoustic thresholds—including sample rate policy,
silence, clipping, noise, dropout, and level tolerances—remain
`CALIBRATION_PENDING` until sanctioned calibration takes exist. No decision may
substitute an existing personal recording or commercial synthetic voice.
