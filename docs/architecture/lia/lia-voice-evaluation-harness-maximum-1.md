# LIA voice evaluation harness

## Authority and boundaries

This harness evaluates a distinct synthetic LIA delivery style. It is not a
voice-cloning, speaker-identification, or reference-speaker similarity system.
No commercial provider is selected, no credentials are required, and no audio
is persisted by the browser adapter.

The authoritative semantic spoken-response layer remains `voiceSpeech.ts`. The
delivery layer may control how that text is rendered, but it must not rewrite
facts, amounts, dates, limitations, evidence status, or safe next actions.

`REFERENCE_MEASUREMENT_PENDING` is true. No sanctioned reference-audio artifact
was available during this work, so the 150–170 words/minute range is an
evaluation target—not a measurement and not a promise made by Web Speech.

## Implemented contracts

- `LiaDeliveryStyle` expresses language, nominal rate, pause intent, question
  contour, restrained expressiveness, emphasis intent, response mode, and
  certainty/limitation category without encoding a provider's proprietary
  controls.
- The browser mapping retains the accepted relative Web Speech rate of `0.94`,
  neutral pitch `1`, volume `1`, and `en-US`. Relative Web Speech rate is never
  reported as absolute WPM.
- Voice inventory discovery normalizes `getVoices()` results, responds to
  `voiceschanged`, prefers explicitly reviewed voice identifiers, then applies
  deterministic English/local/default fallbacks. It makes no gender,
  biometric, accent, or identity inference.
- `LiaSpeechRenderer` defines the future Twelve Hats-owned speech-engine
  boundary. Current browser/device and native-device adapters remain local
  transitional fallbacks. Commercial hosted rendering, vendor voice identity,
  per-render vendor calls, and external production credentials are disallowed.
  Results can report an adapter ID, optional duration and digest, and explicit
  fallback/error state.
- Pronunciation hints are explicit and reviewable. Proposed ACP, LIA, HVAC,
  QBO, and SKU entries are not applied until their status is `APPROVED`; names
  are never guessed.

## Evaluation corpus and measurement

The checked-in corpus has 12 representative responses covering Customer, Job,
currency, percentage, date/time, Payroll readiness, missing evidence,
uncertainty, Beacon, equal-period comparison, Price Book, and an employee-safe
denial. Each item records the canonical visual fact, expected spoken semantic
content, response mode, values that must survive shaping, and prohibited
distortions.

The measurement harness deterministically reports text word count, sentence
count, punctuation/pause intent, response-mode budget, and preservation of
material values. Duration and measured WPM remain unavailable unless an actual
audio duration is supplied. It does not estimate absolute WPM from Web Speech's
relative rate control.

## Privacy and evidence posture

Browser/device speech behavior and processing location vary by browser and
operating system; deployment acceptance must review the actual target devices.
The final renderer must be Twelve Hats-controlled. Any upstream model or
artifact considered for that engine requires an explicit license and training-
data rights review; it is not an exclusive ownership claim. Spoken playback is
a non-authoritative presentation of the visible response. ACP's visual source
and evidence links remain authoritative.

## Enterprise Intelligence handoff

Integrate this candidate after the current spoken-presence authority. Preserve
the `0.94` browser rate unless comparative acceptance produces explicit test
evidence for a change. Review candidate device voices by intelligibility,
warmth, professional credibility, restrained expressiveness, number/date
clarity, limitation delivery, and robotic artifacts—never similarity to a
person. Twelve Hats speech-engine implementation and reference-audio measurement
remain separate, owner-controlled milestones. Commercial provider selection is
not a production milestone.
