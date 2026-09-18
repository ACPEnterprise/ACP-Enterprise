# Twelve Hats pronunciation authority v1

Pronunciation is versioned evidence, not an automatic phonetic guess. Each
entry binds a stable identity, exact term, explicit spoken tokens, language,
lifecycle, reviewer, approval time, and optional predecessor. An accepted
authority binds its complete canonical manifest digest and explicit acceptance
evidence.

`PROPOSED` entries cannot affect owned inference. `APPROVED` entries require
review evidence. `SUPERSEDED` and `REVOKED` entries remain historical but are
not active. Two approved entries cannot compete for the same case-insensitive
term and language.

Every model artifact now binds both pronunciation authority version and digest.
Every inference request must name that exact active version and digest. Missing,
draft, tampered, stale, caller-substituted, or model-mismatched pronunciation
authority fails closed before waveform inference.

This contract does not approve the existing proposed ACP/LIA/QBO/HVAC/SKU
frontend hints, infer names, select phonemes, create audio, or activate a model.
Those entries require human review through a future append-only administration
workflow.
