# LIA delivery style profile and TTS admission packet

## Authority and source status

This packet defines delivery qualities for a **distinct synthetic LIA voice**. It
does not define, store, or optimize a Lianne speaker embedding, voiceprint,
timbre, pitch contour, formant target, accent clone, or similarity score.

`New Recording.m4a` and a reusable intake/segment package were not present in
the sanctioned Laptop1-B filesystem locations during this qualification. No
audio was uploaded, transformed, or copied. Consequently, the numeric ranges
below are product targets derived from the owner-approved desired style, not
measurements attributed to Lianne. Pace, pause, inflection, and accent findings
must remain `REFERENCE_MEASUREMENT_PENDING` until the original or clean local
segments are made available.

When available, local analysis may use speaker separation only to isolate the
reference participant. Outputs must be aggregate delivery statistics and
non-biometric prose. Do not retain speaker embeddings or use speaker similarity
as an acceptance metric.

## Provider-neutral delivery profile

| Dimension | LIA target | Guardrail |
| --- | --- | --- |
| Baseline pace | Moderate, target evaluation range 150–170 words/minute | Vary by content; never treat this range as a measured Lianne value |
| Rate variation | About 0.92–1.06 relative to the selected voice's natural rate | Slower for blockers/evidence, slightly faster for concise confirmations |
| Clause pause | Short, approximately 120–220 ms | Use syntactic boundaries, not pauses after every phrase |
| Sentence pause | Approximately 280–450 ms | Allow 450–650 ms before a correction, limitation, or next action |
| Sentence rhythm | Mix short conclusion, medium explanation, short next step | Avoid report-like lists and repeated equal-length sentences |
| Pitch movement | Low-to-moderate natural variation | No exaggerated upward endings, sing-song delivery, or dramatic range |
| Phrase-final inflection | Settled/downward for facts; gently open for real questions | Do not make declarative evidence sound uncertain |
| Emphasis | One or two meaning-bearing words per sentence | Emphasize status, change, limitation, and action—not every number |
| Warmth | Attentive and calm; contractions are acceptable | Not bubbly, intimate, manipulative, or consoling beyond the evidence |
| Confidence | Direct for known facts; explicitly bounded for gaps | Never use confident prosody to conceal incomplete or conflicting evidence |
| Expressiveness | Moderate-low | Professional conversation, not announcer, theater, sales, or character voice |
| Accent/prosody | Neutral, intelligible US English with natural conversational reduction | No exact accent replication; reference-specific accent remains unmeasured |

### Conversation behaviors

- **Acknowledgement:** brief and functional: “I found it,” “Yes,” or “I can
  check that.” Avoid repeated filler such as “Absolutely!”
- **Clarification:** calm, lightly rising question contour; name the missing
  distinction before asking one concise question.
- **Correction:** small pause, then “Let me correct that” or “The current
  evidence says…” without defensiveness.
- **Uncertainty:** slow slightly and foreground the boundary: “ACP doesn't have
  enough evidence to answer that yet.” Do not whisper or sound apologetic.
- **Bad news/blocker:** steady pace, lower expressiveness, direct fact first,
  then the clearing condition. Avoid alarmist emphasis.
- **Concise answer:** conclusion in one sentence; optionally one short next
  step. Do not read evidence identifiers.
- **Evidence/detail answer:** conclusion, source/as-of boundary, two or three
  supporting facts, limitation, then safe next action. Use measured pauses
  between these layers.
- **Humor/lightness:** rare and situational; never around Payroll, employment,
  money, safety, legal, or missing evidence.

## Current protected TTS implementation

Protected authority uses the browser Web Speech API in
`frontend/src/hooks/useLiaVoice.ts`:

- engine/provider: browser/device-selected `window.speechSynthesis`;
- voice: platform default; no stable ACP voice identity is selected;
- response shaping: first two sentences plus `safe_next_action`, implemented in
  `frontend/src/components/lia/voiceSpeech.ts`;
- configured synthesis parameter: `SpeechSynthesisUtterance.rate = 0.94`;
- unconfigured available properties: `voice`, `lang`, `pitch`, and `volume`;
- pause behavior: punctuation and the device engine; no deterministic pause
  plan;
- style prompting/stability controls: unavailable;
- voice inventory: device-dependent `speechSynthesis.getVoices()`;
- SSML: the API accepts text that may contain SSML, but unsupported devices may
  strip tags, so ACP cannot treat SSML behavior as portable authority;
- audio artifact/delivery evidence: none; playback is ephemeral client output.

The current engine can improve materially through response shaping, bounded
rate/pitch settings, language selection, and explicit device-voice admission.
It cannot guarantee the same voice, cadence, pause realization, or quality
across browsers and operating systems. A stable Twelve Hats voice therefore
requires a future provider/runtime admission, but not before Variant A/B device
acceptance.

## Distinct base-voice requirements

A candidate is acceptable when it is a synthetic adult feminine voice with:

- clear consonants and numbers without an announcer tone;
- calm professional presence at moderate pace;
- warm but restrained affect;
- credible delivery of operational and financial limitations;
- natural questions and corrections;
- low robotic artifacts on Customer names, Job numbers, dates, currency, and
  acronyms;
- stable availability and an explicit provider/OS voice identifier;
- no claim of Lianne similarity.

Reject voices that are bubbly, breathy/intimate, theatrical, sales-like,
overly youthful, aggressively authoritative, or inconsistent across long
evidence sentences.

## Three-variant prototype

### Variant A — current device voice plus spoken-response layer

1. Reconcile the existing dirty spoken-response draft in the dedicated
   `work/lia-spoken-presence-maximum-1` lane; do not overwrite it from this
   packet.
2. Add a typed `LiaDeliveryStyle` configuration with `rate: 0.94`, `pitch: 1.0`,
   `volume: 1.0`, `lang: "en-US"`, sentence budgets, and response modes.
3. Apply the style when constructing `SpeechSynthesisUtterance`.
4. Retain full visual evidence while speaking a conclusion, limitation, and
   next step.
5. Add tests proving missing evidence, source authority, identifiers, and safe
   next actions remain truthful after spoken shaping.

This is the fastest safe improvement. It does not yield a consistent voice
across devices.

### Variant B — best admitted distinct device voice

1. Enumerate `speechSynthesis.getVoices()` after `voiceschanged`.
2. Filter to English feminine-sounding candidates only through an explicit
   reviewed allowlist of installed voice identifiers; never infer gender or
   identity from audio biometrics.
3. Store a local preference by stable voice URI/name plus language, with a
   truthful fallback to the platform default when unavailable.
4. Compare candidates using the ten-response corpus below on the actual target
   Mac/iPhone/browser set.
5. Record intelligibility, warmth, credibility, rhythm, and robotic-artifact
   ratings—never reference-speaker similarity.

Variant B is device-specific and should not be called ACP-wide voice admission.

### Variant C — provider-neutral successor

A provider change is warranted if acceptance requires the same distinct voice
across desktop and mobile, deterministic pause/prosody control, renderable audio,
or provider delivery/quality evidence. Introduce a server-side `LiaSpeechRenderer`
interface only after owner/provider admission. It should accept spoken text,
locale, style profile/version, idempotency identity, and correlation identity,
and return an opaque audio artifact plus engine/voice/style versions. It must not
receive arbitrary database access or hidden business context.

Provider evaluation must score style prompting, rate/prosody/pause control,
voice stability, pronunciation dictionaries, streaming latency, data retention,
training-use policy, regional processing, accessibility, cost, and failover.
No provider is selected by this packet.

## Ten-response comparison corpus

Use identical authoritative/synthetic-safe content for all variants:

1. Customer: identity, two Locations, and one incomplete-history limitation.
2. Job: current status, next Appointment, and a safe Job drill-down.
3. Employee: readiness state without compensation or performance judgment.
4. Scheduling: tomorrow's assigned and unassigned work.
5. Payroll blocker: missing W-4 or accepted time, plus exactly what clears it.
6. Invoice: issued balance versus payment evidence, without calling it revenue.
7. Financial comparison: equal-period revenue and direct-cost change with an
   explicit non-causal explanation.
8. Price Book: draft review candidate with no automatic repricing.
9. Correction: retract an ambiguous Customer/Job reference and ask one concise
   clarification.
10. Missing evidence: state that authoritative material cost is unavailable and
    decline to infer profitability.

Record the same rubric for each: intelligibility, pace, pause placement,
warmth, professional credibility, natural rhythm, limitation delivery,
number/name pronunciation, and robotic artifacts.

## Local reference-analysis procedure

Once the source is present, preserve the original read-only and analyze derived
copies locally:

1. Verify file digest and duration; never rewrite the original.
2. Reuse existing clean segments if their digest/offset manifest exists.
3. Run local voice activity detection and speaker diarization only to select
   clean reference-speaker turns; delete/avoid exporting embeddings.
4. Sample at least 12–20 minutes across opening, explanation, correction,
   question/answer, and casual-business portions rather than one contiguous
   passage.
5. Compute aggregate words/minute, articulation rate excluding silence, pause
   count per minute, median/p75/p90 pause duration, turn length, sentence-length
   distribution, and question/declarative final pitch direction.
6. Review only aggregate outputs plus a small timestamped segment manifest for
   contamination; do not publish transcripts containing private business data.
7. Update this packet by marking each measured claim with source digest, segment
   offsets, tool/version, and confidence. Keep qualitative warmth/humor findings
   explicitly observational.

## Exact implementation handoff

Laptop Enterprise should:

1. Integrate this documentation packet independently.
2. Assign the dirty `voiceSpeech.ts` draft to its current owner for reconciliation.
3. Supply `New Recording.m4a` or the existing segment manifest to Laptop1-B by a
   sanctioned local path; no cloud upload is required.
4. After measurement, implement Variant A in `useLiaVoice.ts` and
   `voiceSpeech.ts`, with tests in `LiaVoicePanel.test.tsx` and a dedicated
   spoken-response corpus test.
5. Run Variant B only on the intended Preview desktop/iPhone devices because
   browser voice inventories are device-dependent.
6. Defer Variant C procurement and credentials to a separately approved provider
   admission milestone.
