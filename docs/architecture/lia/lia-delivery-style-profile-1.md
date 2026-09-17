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

## Current TTS implementation audit

Current Intelligence authority uses two device-owned engines:

- web engine/provider: browser/device-selected `window.speechSynthesis` in
  `frontend/src/hooks/useLiaVoice.ts`;
- mobile engine/provider: `expo-speech` 57.0.3, backed by the installed native
  device speech service in `mobile/src/lia/speech.ts`;
- web voice: normalized `getVoices()` inventory refreshed by `voiceschanged`;
  explicitly reviewed identifiers are preferred when configured, followed by
  deterministic English local/default fallbacks;
- mobile voice: operating-system default for `en-US`; no reviewed mobile voice
  identifier is currently admitted;
- response shaping: first two sentences plus `safe_next_action`, implemented in
  `frontend/src/components/lia/voiceSpeech.ts` for web. Mobile speaks the
  server-composed answer and does not invent a second semantic renderer;
- configured controls: relative rate `0.94`, pitch `1`, volume `1` on web, and
  language `en-US`; mobile maps language, relative rate, and pitch;
- pause behavior: punctuation and the device engine; no deterministic pause
  duration control;
- style prompting/stability controls: unavailable;
- expressiveness control: semantic `RESTRAINED` intent exists, but current
  device engines do not expose a portable expressiveness or stability control;
- SSML/prosody: not a portable Web Speech or `expo-speech` contract and not used
  by ACP; markup must not be passed expecting deterministic interpretation;
- audio artifact/delivery evidence: none; playback is ephemeral client output.

On the qualifying macOS 26.5.2 host, the installed command-line voice inventory
included multiple English voices, including Samantha and Kathy, plus regional
English voices. This proves only device inventory—not browser availability,
quality, gender suitability, or product admission. Runtime `getVoices()` and an
on-device human review remain authoritative for Variant B.

The present stack can improve phrasing, language choice, relative rate,
pitch/volume, and device-voice selection. It cannot guarantee the same voice,
pause timing, cadence, or quality across browsers and operating systems. A
provider successor is warranted only if cross-device acceptance proves those
limits material; it is not warranted merely because richer controls exist
elsewhere.

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

**Status: implemented in current Intelligence authority.**

The typed `LiaDeliveryStyle`, `0.94` relative browser rate, neutral pitch,
language, response modes, spoken semantic renderer, and invariant tests are in
place. Full visual evidence remains authoritative. Device acceptance is still
required because relative rate is not an absolute WPM guarantee.

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
Inventory discovery, stable preference rules, and fallback are implemented.
No voice has been admitted as “best”: that requires the same 12-item corpus to
be reviewed on the intended Preview Mac/browser and iPhone, using quality—not
similarity to Lianne—as the rubric.

### Variant C — provider-neutral successor

A provider change would be warranted if acceptance requires the same distinct voice
across desktop and mobile, deterministic pause/prosody control, renderable audio,
or provider delivery/quality evidence. Introduce a server-side `LiaSpeechRenderer`
interface only after owner/provider admission. It should accept spoken text,
locale, style profile/version, idempotency identity, and correlation identity,
and return an opaque audio artifact plus engine/voice/style versions. It must not
receive arbitrary database access or hidden business context.

Provider evaluation must score style prompting, rate/prosody/pause control,
voice stability, pronunciation dictionaries, streaming latency, data retention,
training-use policy, regional processing, accessibility, cost, and failover.
The provider-neutral `LiaSpeechRenderer` request/result boundary now exists in
`voiceDelivery.ts`; no external adapter is implemented and no provider is
selected by this packet.

## Twelve-response comparison corpus

Use the checked-in `liaVoiceEvaluationCorpus` for all variants. It includes the
ten categories below plus explicit percentage/date-time and employee-safe
denial coverage:

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

1. Integrate this corrected current-state packet independently.
2. Supply `New Recording.m4a` or the existing segment manifest to Laptop1-B by a
   sanctioned local path; no cloud upload is required.
3. Run Variant B only on the intended Preview desktop/iPhone devices because
   browser voice inventories are device-dependent.
4. Record reviewed device voice identifiers only after the 12-item comparison;
   do not infer voice attributes from name or audio biometrics.
5. Defer Variant C procurement and credentials to a separately approved provider
   admission milestone.
