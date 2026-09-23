# LIA Delivery Naturalness 1

Status: `WORKER_ASSIGNMENT_REQUIRED`

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
