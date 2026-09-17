# Twelve Hats Speech engine foundation v1

## Decision and current state

`TWELVE_HATS_SPEECH` is the sole production target for LIA speech. Browser Web
Speech and native Expo speech remain transitional device fallbacks. This
foundation contains no model weights, pretrained checkpoint, speech dataset,
vocoder, provider client, credential, hosted inference call, or fake waveform.

The internal Python package is `app.twelve_hats_speech`. It owns typed contracts,
canonical manifest hashing, rights-gated training admission, artifact
verification, lifecycle governance, and a fail-closed engine scaffold. It is not
registered as an API route and cannot claim `INFERENCE_READY`.

## Owned system decomposition

The eventual system is decomposed so each artifact can be selected, trained,
versioned, and qualified independently:

1. deterministic text normalization consuming LIA's already-authoritative
   semantic spoken text;
2. approved pronunciation authority and phoneme representation;
3. linguistic encoder;
4. duration, pause, and prosody model consuming `LiaDeliveryStyle` intent;
5. acoustic representation/model;
6. waveform generator/vocoder;
7. bounded inference scheduler and resource admission;
8. optional streaming/chunk assembler;
9. verified model cache; and
10. immutable artifact registry and promotion evidence.

No final neural architecture is selected. A later evidence-based decision must
compare at least an autoregressive versus parallel acoustic path and direct
waveform versus intermediate-representation plus vocoder path. Selection must
measure naturalness, intelligibility, training complexity, CPU/GPU memory,
first-audio and full-render latency, streaming behavior, reproducibility,
cross-platform delivery, license obligations, and complete ownership of the
trained voice artifacts. No option may assume pretrained weights.

## Dataset and training admission

`SpeechDatasetVersion` is a compatibility boundary for the future rights/data
ledger. `QUALIFIED` requires an immutable provenance digest, admitted time,
rights-evidence digest, and either `TWELVE_HATS_OWNED` or
`COMMISSIONED_PERPETUAL_COMMERCIAL` rights. Missing, ambiguous, rejected, or
revoked rights fail closed.

`SpeechTrainingRun` binds the exact configuration and digest, code revision,
dataset version, architecture version, seeds, hardware profile, checkpoints,
metrics schema, failures, output digests, and evaluator results. Training
admission rejects unqualified rights, mismatched dataset versions, and modified
configuration. This foundation does not start a training process.

## Artifact and lifecycle governance

Each `SpeechModelArtifact` binds model and architecture versions, code revision,
dataset and training run, training configuration, pronunciation authority,
evaluation corpus, artifact hashes, creation time, qualification, promotion,
and its own canonical manifest digest.

Promotion is append-only authority represented by `DEVELOPMENT`, `CANDIDATE`,
`QUALIFIED`, `ACCEPTED`, `SUPERSEDED`, or `REVOKED`. `ACCEPTED` is structurally
invalid unless qualification is `QUALIFIED`. Rendering accepts only an exact
active version whose manifest and all artifact hashes verify. Revoked,
superseded, candidate, failed, unknown, or caller-selected arbitrary artifacts
cannot render.

## Internal inference boundary

The future transport may expose an authenticated internal-only endpoint such as
`POST /internal/v1/twelve-hats-speech/render`, but no route is activated now.
The service contract is `SpeechInferenceRequest` to `SpeechInferenceResult`.
It accepts bounded semantic text, language, response mode, delivery metadata,
approved pronunciation version/digest, request identity, and optional exact
active model version. It contains no provider ID, external URL, credential,
filesystem path, arbitrary model selector, or hidden business context.

Before transport activation, security review must require:

- authenticated workload identity and explicit internal permission;
- private network exposure only, with no public arbitrary-render endpoint;
- request/body, concurrency, duration, and compute quotas;
- allowlisted accepted model versions loaded only through the artifact registry;
- tenant/correlation binding only when necessary for authorization and audit;
- no model-path or artifact-reference input from callers;
- safe failure classes without model paths, text, secrets, or stack traces;
- render audit containing model, dataset, pronunciation, renderer, request
  digest, and outcome—but not sensitive spoken text or audio by default.

## Audio delivery

The contract can represent PCM S16LE or WAV for deterministic internal
qualification, FLAC for lossless custody, and Opus or AAC candidates for web,
iPhone, Android, and future telephone delivery. This list is capability
vocabulary, not a codec selection. Each result binds content type, sample rate,
duration, streaming capability, and render digest.

Default caching is no persistent business-sensitive audio. An ephemeral,
private render cache may be admitted later only with request/model/style digest
keys, short explicit lifetime, encryption, tenant isolation where applicable,
and deletion evidence. Audio references must be opaque and authorized; local
filesystem paths are never domain authority.

## Semantic and acoustic evaluation

Semantic correctness remains owned by the LIA spoken renderer and existing
12-item corpus: facts, signs, amounts, percentages, dates, times, counts,
limitations, and safe next actions must survive unchanged.

`SpeechAcousticEvaluation` separately reserves evidence for intelligibility,
pronunciation, pacing, pause behavior, number/currency accuracy, acronym
handling, clipping/artifacts, consistency, latency, and owner preference. It
cannot record scores while status is `MODEL_ACOUSTIC_EVALUATION_PENDING`, and an
evaluated result requires audio and evaluator evidence digests. No acoustic
score exists today.

## Reproducibility and operations

Canonical JSON uses sorted keys, compact separators, UTF-8/ASCII-safe encoding,
explicit versions, SHA-256 digests, immutable timestamps, and exact Git
revisions. Reproducing a candidate requires the admitted dataset manifest,
rights evidence, source revision, architecture implementation, exact config,
seeds, hardware profile, checkpoints, pronunciation authority, corpus version,
and evaluator results.

The engine state vocabulary is `NOT_CONFIGURED`, `DATASET_NOT_READY`,
`TRAINING_NOT_READY`, `MODEL_NOT_AVAILABLE`, `MODEL_AVAILABLE`,
`INFERENCE_READY`, and `FAILED`. The current scaffold truthfully reports
`MODEL_NOT_AVAILABLE`, `MODEL_AVAILABLE` only for a verified accepted artifact,
or `FAILED`; it never reports `INFERENCE_READY` because synthesis is absent.

## Remaining decisions

- admit a rights-cleared Twelve Hats dataset through the future authoritative
  rights ledger;
- select an owned-from-scratch architecture after compute/quality experiments;
- select general-purpose runtime libraries after license/security review;
- establish isolated training compute and reproducibility images;
- implement and qualify model loading, synthesis, resource isolation, and
  internal transport;
- conduct acoustic and cross-platform acceptance before promotion.

These are evidence gates, not permission to download models or data.
