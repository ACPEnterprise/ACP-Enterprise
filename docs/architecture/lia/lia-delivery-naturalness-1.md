# LIA Delivery Naturalness 1

Status: `QUALIFIED_CANDIDATE`

## Current defect

The semantic spoken renderer is qualified for factual preservation, but the
delivery path remains mechanical. `spokenAnswer()` emits one cleaned string,
and `useLiaVoice()` sends it as one browser `SpeechSynthesisUtterance` with
relative rate `0.94`, pitch `1`, and volume `1`. `LiaDeliveryStyle` records
pause, contour, limitation, and emphasis intent, but the browser adapter does
not realize those controls. Thought-group timing, selective emphasis, and
question/warning cadence are therefore absent.

This is a delivery/prosody defect, not a semantic-answer defect and not a
reason to select an arbitrary replacement device voice.

## Bounded successor assignment

Assign the next available Laptop-A LIA worker after its current Pipeline
checkpoint:

`LIA.DELIVERY.NATURALNESS.1`

Implement the smallest shared Web/Mobile-compatible delivery contract that can
materially improve naturalness without changing semantic text, facts,
authority, uncertainty, identity, amounts, dates, counts, or actions. Preserve
the current semantic renderer as the sole meaning authority.

Required deterministic intents:

- `NEUTRAL_EXPLANATION`
- `CONCISE_ANSWER`
- `CLARIFICATION`
- `QUESTION`
- `REASSURANCE`
- `WARNING`
- `EXCEPTION`
- `OWNER_BRIEF`
- `STEP_BY_STEP`

Use thought-group segmentation, bounded phrase pacing, semantic micro-pauses,
selective emphasis, and restrained question/limitation/warning delivery. Keep a
safe fallback when the platform cannot realize a requested control. Do not
claim absolute WPM from a platform-relative rate.

## Acceptance corpus and A/B path

Existing semantic corpus:

- `frontend/src/components/lia/voiceAcceptanceCorpus.ts`
- `frontend/src/components/lia/voiceSpeech.test.ts`
- `frontend/src/components/lia/voiceDelivery.test.ts`

Add a naturalness evaluation layer using identical semantic content:

- A: current single-utterance delivery
- B: naturalness successor delivery

Cover factual answer, owner brief, clarification, missing data, Payroll
blocker, Dispatch warning, positive result, step-by-step instruction,
economic explanation, and Customer/Employee context. Assert semantic
equivalence before manual listening.

Manual scoring remains owner acceptance: human quality, pace, pauses, warmth,
confidence, clarity, over-enunciation, endings, question naturalness, and
overall preference.

## Implemented successor

The semantic renderer remains unchanged. Its exact result is normalized once,
then a deterministic `lia-delivery-plan.v1` partitions it into semantic thought
groups. Sentence boundaries, explanatory clause boundaries, long-clause
commas, questions, warnings, and ordered steps inform grouping. Each group
retains an exact substring of the semantic answer; joining the groups must
reproduce the normalized semantic text before playback is admitted.

Delivery intents are `CONCISE_ANSWER`, `NEUTRAL_EXPLANATION`,
`CLARIFICATION`, `QUESTION`, `REASSURANCE`, `WARNING`, `OWNER_BRIEF`, and
`STEP_BY_STEP`. Relative device pacing is bounded from `0.86` through `1.0`,
pauses from `170` through `300` milliseconds, and pitch from `0.985` through
`1.035`. Material-value, missing-evidence, conflict, and ordered-action groups
receive restrained slower delivery. Questions receive a gentle final rise;
warnings remain calm and slightly lower. These are relative provider controls,
not absolute acoustic claims.

Web queues one `SpeechSynthesisUtterance` per thought group and advances only
after the prior group completes plus its semantic pause. Cancellation and
barge-in invalidate the rest of the plan. Mobile applies the same intent,
grouping, bounds, pause, sequencing, and cancellation behavior through the
existing Expo device-local fallback. Neither path changes evidence or selects
a commercial provider.

The deterministic A/B corpus contains ten required delivery families. A is
the prior single fixed-rate utterance; B is the delivery plan over identical
semantic text. Automated admission requires exact normalized semantic
equivalence and preservation of every declared material value. Human listening
remains the authority for perceived warmth and naturalness because browser and
device speech engines vary.

## Transitional and permanent architecture

Current Web Speech and native device speech remain transitional local fallbacks;
they cannot guarantee a stable expressive identity across devices.

The permanent target remains:

`LIA semantic renderer -> Twelve Hats delivery/prosody -> TWELVE_HATS_SPEECH`

The owned successor must support self-hosted inference, Twelve Hats model and
voice-artifact custody, a versioned pronunciation lexicon, cross-device
rendering, shared Web/Mobile semantics, and an explicit fallback state. No
commercial TTS dependency, credentials, voice cloning, or provider purchase is
authorized by this assignment.
