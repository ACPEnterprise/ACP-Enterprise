# LIA Voice Sovereignty v1

## Hard product rule

The production LIA voice belongs only to Twelve Hats. Twelve Hats controls the
voice identity, approved pronunciation authority, speech engine/model,
inference infrastructure, deployment, and lifecycle. No commercial TTS
provider, third-party named voice, per-render vendor service, vendor runtime
dependency, or external production speech credential may control the LIA voice
path.

Current browser Web Speech and native Expo device speech are useful local,
transitional fallbacks for development and acceptance. They are not LIA's
permanent voice identity and must not be described as the final production
architecture.

## Owned production pipeline

```text
LIA intelligence and authorized evidence
  -> Twelve Hats spoken semantic renderer
  -> Twelve Hats LiaDeliveryStyle and pronunciation authority
  -> Twelve Hats-controlled speech engine/model
  -> Twelve Hats-controlled inference infrastructure
  -> audio
```

The semantic renderer is presentation-only. It cannot derive facts, bypass
authorization, access raw source records, or change amounts, dates, counts,
uncertainty, evidence availability, or safe next actions.

## Ownership and rights

### Voice identity

The production identity is a distinct synthetic LIA identity owned and
controlled by Twelve Hats. It is not leased from a provider, tied to a
provider-named voice, cloned from a person, or evaluated through biometric
similarity.

### Training data

Any training or adaptation data must be Twelve Hats-owned or explicitly
commissioned/licensed for perpetual Twelve Hats commercial synthetic-speech
use. Provenance, consent, license scope, retention, and revocation terms must
be recorded. Ambiguous scraped data and employee-derived voice data without
explicit rights are prohibited.

### Model and inference

The target is Twelve Hats-controlled model artifacts/weights and Twelve
Hats-controlled inference infrastructure with no required external speech API.
An upstream model may be evaluated only with an explicit license review and
must remain classified as a non-exclusive dependency; it cannot be represented
as Twelve Hats-exclusive ownership.

### Pronunciation and delivery

Twelve Hats owns a versioned, reviewable pronunciation authority and the
`LiaDeliveryStyle` contract: response modes, nominal pace, pause intent,
question contour, emphasis, and bounded uncertainty delivery. Built-in safe
normalization remains limited to approved deterministic entries. Arbitrary
people names are never guessed; product-specific entries such as SKU require
review before activation.

## Renderer boundary

`LiaSpeechRenderer` is the stable adapter boundary for the final
`TWELVE_HATS_SPEECH` engine. Its bounded request may contain spoken semantic
text, locale, response mode, delivery style/version, approved pronunciation
data, and response identity. Its result may contain readiness/failure state,
renderer/model/voice/style versions, render digest, duration metadata, and a
bounded error class.

The renderer receives no arbitrary database access, hidden business context,
authorization authority, or mutation capability. Browser Web Speech and Expo
Speech implement transitional local adapters only. Commercial hosted adapters
and vendor-controlled voice identities are disallowed for production.

## Privacy and portability

Production LIA text and production voice recordings must not be sent to an
outside TTS vendor for inference or training. The owned identity and delivery
contract must be portable across Mac, Web, iPhone, Android, and any future
phone channel. Current local adapters may differ acoustically, but equivalent
responses must preserve the same facts, signs, percentages, dates, times,
counts, uncertainty, provenance, evidence availability, and next-action
meaning.

## Current status and gates

| Capability | Status |
| --- | --- |
| Web Speech / browser device engine | `TRANSITIONAL_LOCAL_FALLBACK` |
| Expo native device speech | `TRANSITIONAL_LOCAL_FALLBACK` |
| Twelve Hats-owned speech engine | `TARGET_NOT_IMPLEMENTED` |
| Commercial production TTS | `DISALLOWED` |
| Provider credentials or purchase | `NONE` |
| Reference measurement from unavailable audio | `REFERENCE_MEASUREMENT_PENDING` |

The owned engine requires a separately approved architecture and privacy
review, rights-cleared training-data ledger, model/license decision, security
review, deployment qualification, cross-platform evaluation, and owner
acceptance. This mission does not build the neural engine or select a provider.
