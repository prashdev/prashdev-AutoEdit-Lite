# AutoEdit-Lite Project Status

This file is the authoritative handoff and progress ledger for the project.
Read it before making changes. Do not infer completion from old conversation
history, passing unit tests alone, or the existence of build artifacts.

## Status Snapshot

- **Last updated:** 2026-06-13
- **Current objective:** Reach 95% human-editor agreement for 3-7 minute
  vertical talking-head videos while keeping every setup/build artifact below
  400 MiB.
- **Overall status:** Active; implementation and deterministic verification
  have advanced substantially, but the 95% agreement target is not yet proven.
- **Estimated implementation progress:** 95% complete; approximately 5% of
  the implementation and evaluation work remains.
- **Measured goal progress:** Not yet measurable against the required 95%
  human-editor agreement because no representative human-labelled dataset has
  been evaluated.
- **Current step:** Collect, human-label, render, and evaluate at least 10
  complete actual representative cases for each target language.
- **Current iteration progress:**
  - Audit required-output completeness: 100%
  - Record selected defect in every project Markdown file: 100%
  - Add and verify failing regression: 100%
  - Implement required-output reliability gate: 100%
  - Full verification, artifact rebuild, and final documentation refresh: 100%
- **Primary remaining proof:** Run representative 3-7 minute videos against
  human-editor keep/remove, cut-boundary, and story-meaning labels.
- **Latest source verification:** `322 passed`
- **Latest installer verification:** Build succeeded; embedded CLI starts.
- **Latest artifact sizes:**
  - `installer/dist/AutoEditLite-Setup.exe`: 234.75 MiB
  - `installer/dist/AutoEditLite-Portable-0.2.0.zip`: 315.89 MiB
- **Model packaging:** No Whisper or other large speech-model weights are
  bundled; dependency-owned assets include a 1.19 MiB Silero VAD model and
  tiny ONNX Runtime samples.

## Accuracy Area Status

| Area | Status | Current evidence | Remaining proof or work |
|---|---|---|---|
| Transcription accuracy | Implemented, evaluator available; not benchmark-proven | Sarvam AI preferred for Marathi, Hindi, and Indian English; word timestamps explicitly requested and invalid or chronologically backward word entries filtered; Unicode-aware WER evaluation requires at least 95% accuracy per case, overall, and per target language; Whisper fallback retained | Run against representative reference transcripts |
| Pause removal | Implemented, deterministic tests pass | Project-wide short-form threshold is 0.5 seconds; word-timestamped gaps are detected and removed, and Sarvam creates matching editorial units around longer gaps | Human review on real speech pacing |
| Filler removal | Implemented, deterministic tests pass | English and Devanagari fillers, punctuation-qualified ambiguous sentence-start fillers, and false starts covered | Human review for false positives/negatives |
| Repetition removal | Implemented with meaning safeguards | Cleaner directly similar take preferred; explicit and common contracted negation contrasts, high-confidence semantic opposites, materially different English/Marathi/Hindi quantities, and transitive-only distinct statements are preserved | Human-labelled repeated-take benchmark |
| Topic relevance | Implemented, deterministic tests pass | General recurring-topic inference and IVF/fertility profiles; isolated tangents are rejected | Human-labelled topic-drift benchmark |
| Keep/remove decisions | Implemented, evaluator available | Pre-selection scores use whole-word lexical signals; deterministic refinement; duration-weighted balanced evaluator canonicalizes same-decision human intervals, rejects contradictory system decisions, and cannot pass the 95% gate without at least 10 distinct actual source videos per target language; ffprobe must confirm video, audio, 9:16 geometry, and 180-420 second duration | Representative human-labelled dataset |
| Cut boundaries | Implemented, deterministic/render tests pass | Negative/non-finite selected timestamps and post-clamp sub-0.5-second micro-cuts are rejected; word-boundary snapping, whole-word captions, natural contiguous-range merge, and one-to-one start/end boundary agreement measurement are enforced | Human boundary agreement on real videos |
| 90-second story accuracy | Implemented with safeguards | Context-dependent conclusions and anaphoric pronoun fragments require the nearest substantive premise while removable filler may be skipped; self-contained demonstrative noun phrases remain eligible; duration trimming avoids orphaning conclusions and refuses whole-range removals that would push the story below the 85% minimum; every representative case requires a rendered output that passes 85%-110% duration, 1080x1920 geometry, audio-presence, and A/V-sync validation plus a valid timeline-bounded SRT and matching per-run accuracy report; story-meaning label required for pass | Human confirmation that final stories preserve meaning |
| B-roll suggestions | Implemented, evaluator available | Timestamped, concept-level, retained-word-grounded, clause-scoped negation-aware suggestions including comma-conjoined independent clauses; suggestion-only mode; one-to-one human relevance ratings required to reach 95% overall and independently per target language | Representative human-rated B-roll dataset |

## Completed And Verified Work

1. Added Sarvam-first transcription for supported Indian languages with
   isolated job outputs and timestamp normalization.
2. Kept local faster-whisper as an offline fallback without bundling model
   weights in the installer.
3. Tightened short-form silence handling to 0.5 seconds and improved filler,
   false-start, and repeated-take detection.
4. Added pre-selection editorial scoring for topic relevance, clarity, hook
   strength, speaker confidence, transcription confidence, uniqueness,
   usefulness, emotional value, repetition, filler, off-topic drift, and
   context dependency.
5. Added topic-consistency safeguards, including IVF/fertility domain support
   and protection against isolated specialized tangents.
6. Added word-boundary cut snapping, subtitle clipping, and whole-word subtitle
   inclusion.
7. Added story-fill fallback, context-dependent story preservation, and
   transcript-aware duration trimming.
8. Added negation-aware repetition and false-start protection so corrective
   contrasts are not removed as duplicates.
9. Added timestamped B-roll suggestions grounded only in retained spoken words;
   negated statements use neutral explanatory suggestions.
10. Added required JSON outputs: `edit_decisions.json`,
    `broll_suggestions.json`, and `accuracy_report.json`.
11. Added human-agreement evaluation using duration-weighted balanced
    keep/remove agreement, one-to-one cut-boundary matching, and mandatory
    story-meaning assessment.
12. Added dataset-level accuracy aggregation and strict invalid-label handling.
13. Added final video validation for 9:16 geometry, audio presence, the
    85%-110% target-duration range, and audio/video drift.
14. Added audio edge fades, async resampling, and contiguous-range merging for
    more natural, synchronized cuts.
15. Rebuilt and audited installer/portable artifacts below 400 MiB with no
    bundled model weights.
16. Replaced substring-based hook, confidence, usefulness, and emotional
    signal matching with whole-word matching so unrelated words do not receive
    inflated editorial scores.
17. Prevented transitive duplicate groups from penalizing statements that are
    not directly similar to the preferred retained take.
18. Preserved context-dependent conclusions when rejected filler or a weak
    aside separates them from their nearest retained substantive premise.
19. Corrected human-agreement measurement to score start and end cuts as
    separate one-to-one boundary decisions instead of all-or-nothing ranges.
20. Protected semantic sentence-start phrases such as "right now", "right
    here", and "now is" while retaining punctuated discourse-filler removal.
21. Canonicalized overlapping or touching same-decision human labels before
    agreement measurement so one continuous edit does not create extra cuts.
22. Rejected contradictory overlapping system keep/remove rows so invalid
    output cannot receive a valid agreement score or pass the dataset gate.
23. Protected high-confidence semantic opposites such as safe/unsafe,
    increases/decreases, and before/after from repeated-take and false-start
    removal while retaining detection of true duplicates that mention both.
24. Protected materially different digit-based and written-number claims from
    repeated-take and false-start removal while retaining identical numeric
    duplicate detection.
25. Extended written-number protection to common Marathi and Hindi cardinal,
    scale, fraction, and ordinal words used in primary target-language videos.
26. Scoped B-roll negation handling by clause so unrelated negative statements
    do not suppress relevant visuals for a separate affirmative service claim.
27. Extended B-roll clause scoping to comma-plus-conjunction independent
    clauses while preserving neutral suggestions for negated service lists.
28. Extended negation meaning safeguards to common English contractions such
    as `didn't`, `hasn't`, `shouldn't`, and `couldn't` across editorial
    repetition scoring and word-level false-start detection.
29. Added predicate-aware anaphoric-fragment detection so unsupported lines
    such as `This helps...` require a substantive premise while self-contained
    lines such as `This video explains...` remain selectable.
30. Aligned Sarvam utterance segmentation with the project-wide 0.5-second
    short-form pause threshold so awkward gaps create precise editorial and
    cut-boundary units without splitting exact half-second natural pauses.
31. Filtered blank, non-finite, negative, and non-positive Sarvam word
    timestamp entries before segmentation so invalid provider data cannot
    shift spoken boundaries into silence or contaminate word-level cuts.
32. Rejected Sarvam word timestamp entries whose start or end moves backward
    relative to the prior accepted word, preserving chronological editorial,
    subtitle, and cut-boundary data.
33. Rejected negative and non-finite Claude-selected source timestamps before
    word snapping and FFmpeg processing so malformed model output cannot create
    invalid cut boundaries.
34. Revalidated selected range duration after source-end clamping and
    chronology normalization so valid-looking model ranges cannot become
    unnatural sub-0.5-second micro-cuts.
35. Prevented duration enforcement from knowingly removing whole segments or
    whole words when every available removal would push the final story below
    the accepted 85% minimum.
36. Added a representative dataset-coverage gate requiring 3-7 minute, 9:16,
    90-second target cases across Marathi, Hindi, and Indian English before
    aggregate agreement can report that the 95% goal is met.
37. Made dataset agreement score the complete declared source timeline,
    including pause/dead-air intervals omitted by both decision files, and
    reject system or human ranges outside the source duration.
38. Added per-language reliability reporting and made the dataset 95% gate
    require Marathi, Hindi, and Indian English to each independently meet the
    agreement target.
39. Added unique retained-edit duration measurement, rejected out-of-source
    actual cut ranges, and made dataset success require every actual edit to
    stay within 85%-110% of its declared target duration.
40. Added one-to-one human relevance rating for generated B-roll suggestions
    and made dataset success require at least 95% relevance overall and
    independently for Marathi, Hindi, and Indian English.
41. Added Unicode-aware word-error-rate measurement against human reference
    transcripts and made dataset success require at least 95% transcription
    accuracy per case, overall, and independently per target language.
42. Required an existing source-video path and at least 10 distinct source
    videos for each target language before representative coverage can pass.
43. Added ffprobe-backed representative source-media validation requiring
    video, audio, 9:16 geometry, and an actual 180-420 second duration; actual
    measured duration now drives agreement scoring.
44. Required every representative case to include a rendered output video
    that passes final duration, 1080x1920 geometry, audio-presence, and A/V-sync
    validation before the dataset can report 95% success.
45. Required every representative case to include a nonempty chronological SRT
    within the rendered timeline and an accuracy report whose target duration
    matches the case and records valid final-output evidence.

## Latest Verification Evidence

Run after the required-output reliability gate change and installer rebuild:

```text
py -m pytest -q
322 passed

AutoEditLite-Setup.exe            234.75 MiB  under 400 MiB
AutoEditLite-Portable-0.2.0.zip   315.89 MiB  under 400 MiB
AutoEditLite-Portable-0.1.0.0.zip 317.30 MiB  under 400 MiB

Staged source hashes match:
accuracy_outputs.py, accuracy_dataset.py, captions.py, filler_detector.py,
analyze.py, editor.py, output_validation.py, transcribe.py

Staged model-asset audit:
No Whisper or other large speech-model bundle. Largest dependency-owned model
asset is faster-whisper's 1.19 MiB Silero VAD ONNX file; remaining ONNX Runtime
samples are tiny.

Portable CLI: exit code 0

Markdown status coverage:
README.md, PROJECT_STATUS.md, and installer/README.md all contain a status
section and link to this authoritative ledger.
```

Earlier production-path render verification used bundled FFmpeg and produced a
1080x1920 video with audio, expected duration, and 0.0 seconds measured A/V
drift.

## Not Yet Proven

- The project has **not** demonstrated 95% human-editor agreement.
- There is no representative human-labelled video dataset in the repository.
- Deterministic tests prove specific behaviors, not the requested real-world
  agreement percentage.
- The goal must remain active until representative evaluation reaches at least
  95% and every reviewed final story preserves meaning.

## Next Best Actions

1. Create a representative labelled dataset with at least 10 distinct source
   videos each for Marathi, Hindi, and Indian English in the 3-7 minute range.
2. Record human keep/remove intervals, cut boundaries, and
   `story_meaning_preserved` for every case.
3. Run AutoEdit-Lite on each case and aggregate results with
   `accuracy_dataset.py`.
4. Inspect the largest disagreement categories and improve the highest-impact
   failure mode using test-driven development.
5. Rebuild and re-audit setup artifacts after every shipped-code change.

## New Session Start Here

Before editing:

```powershell
git status --short
py -m pytest -q
```

Then read:

1. `PROJECT_STATUS.md`
2. `README.md`
3. The relevant source and tests for the next accuracy gap

Do not touch or delete `installer/nuke.ps1`; it is a pre-existing untracked
file.

## Documentation Update Protocol

After every meaningful completed step:

1. Update this file's **Status Snapshot**, relevant area row, completed-work
   list, verification evidence, and next actions.
2. Update the **Project Status** section in `README.md`.
3. Update the **Project Status** section in `installer/README.md`, even when the
   completed step does not directly affect the installer.
4. Before starting a long or credit-intensive operation, record the intended
   operation in the current-status line. After it finishes, replace that line
   with the result and evidence.
5. Never write "95% achieved" unless representative human-labelled evaluation
   proves it.

If another project Markdown file is added later, give it a **Project Status**
section that links here and include it in every meaningful status refresh.

This protocol is intended to prevent future sessions from repeating completed
work, overstating progress, or spending credits reconstructing project state.

## Progress Log

| Date | Step | Result |
|---|---|---|
| 2026-06-13 | Required-output reliability gate and artifact audit | The 95% gate now requires every representative case to include a valid timeline-bounded SRT and matching per-run accuracy report in addition to decisions, B-roll, transcript, and rendered output evidence; rebuilt artifacts and final audit pass with 322 tests; setup is 234.75 MiB, latest portable is 315.89 MiB, all artifacts are below 400 MiB, staged sources match, portable CLI exits 0, and no large speech model is bundled; all iteration steps are 100% complete |
| 2026-06-13 | Required-output reliability artifact rebuild | Setup and portable artifact rebuild succeeded; verification/rebuild/docs is 75% complete pending final acceptance checks and evidence refresh |
| 2026-06-13 | Full source verification before required-output rebuild | Full suite passes with 322 tests; embedded-runtime compilation and diff checks pass; verification/rebuild/docs is 50% complete |
| 2026-06-13 | Required-output reliability gate implementation | Every representative case now requires a valid nonempty SRT within the rendered timeline and an accuracy report whose target duration matches the case and records valid final-output evidence; all 19 dataset evaluator tests pass; broader verification in progress |
| 2026-06-13 | Required-output completeness regression verified red | An otherwise-perfect 30-case representative dataset with valid renders but no subtitles or per-run accuracy reports has no required-output reliability result and can satisfy the current 95% gate; implementation in progress |
| 2026-06-13 | Started required-output completeness evaluation | The representative 95% gate can pass without edited_90s.srt or accuracy_report.json even though both are required deliverables; regression fix in progress |
| 2026-06-13 | Rendered-output reliability gate and artifact audit | The 95% gate now requires every representative case to include a rendered output that passes final duration, 1080x1920 geometry, audio-presence, and A/V-sync validation; rebuilt artifacts and final audit pass with 321 tests; setup is 234.76 MiB, latest portable is 315.89 MiB, all artifacts are below 400 MiB, staged sources match, portable CLI exits 0, and no large speech model is bundled; all iteration steps are 100% complete |
| 2026-06-13 | Rendered-output reliability artifact rebuild | Setup and portable artifact rebuild succeeded; verification/rebuild/docs is 75% complete pending final acceptance checks and evidence refresh |
| 2026-06-13 | Full source verification before rendered-output rebuild | Full suite passes with 321 tests; embedded-runtime compilation and diff checks pass; verification/rebuild/docs is 50% complete |
| 2026-06-13 | Rendered-output reliability gate implementation | Every representative case now requires an actual rendered output that passes final duration, 1080x1920 geometry, audio-presence, and A/V-sync checks; all 18 dataset evaluator tests pass; broader verification in progress |
| 2026-06-13 | Rendered-output reliability regression verified red | An otherwise-perfect 30-case representative dataset with no rendered videos has no rendered-output reliability result and can satisfy the current 95% gate; implementation in progress |
| 2026-06-13 | Started rendered-output reliability evaluation | The representative 95% gate can pass without any actual edited_90s.mp4 evidence, so decision agreement does not prove final duration, vertical framing, audio presence, or A/V sync; regression fix in progress |
| 2026-06-13 | Actual source-media reliability gate and artifact audit | The 95% gate now ffprobes every representative source and requires actual video, audio, 9:16 geometry, and 180-420 second duration; measured duration drives agreement scoring; rebuilt artifacts and final audit pass with 320 tests; setup is 234.74 MiB, latest portable is 315.89 MiB, all artifacts are below 400 MiB, staged sources match, portable CLI exits 0, and no large speech model is bundled; all iteration steps are 100% complete |
| 2026-06-13 | Actual source-media reliability artifact rebuild | Setup and portable artifact rebuild succeeded; verification/rebuild/docs is 75% complete pending final acceptance checks and evidence refresh |
| 2026-06-13 | Full source verification before actual source-media rebuild | Full suite passes with 320 tests; embedded-runtime compilation and diff checks pass; verification/rebuild/docs is 50% complete |
| 2026-06-13 | Actual source-media reliability gate implementation | Representative coverage now probes every source and requires video, audio, 9:16 geometry, and actual 180-420 second duration; measured duration drives agreement scoring; all 17 dataset evaluator tests pass; broader verification in progress |
| 2026-06-13 | Actual source-media reliability regression verified red | Thirty distinct non-video placeholders with perfect manifest claims still have no actual-media validity result and can satisfy existing representative coverage; implementation in progress |
| 2026-06-13 | Started actual source-media reliability evaluation | Representative coverage only checks that source files exist and trusts declared duration and 9:16 metadata, so placeholders or non-target media can count toward the 95% proof; regression fix in progress |
| 2026-06-13 | Minimum distinct-case reliability gate and artifact audit | The 95% gate now requires existing source-video evidence and at least 10 distinct videos per target language; rebuilt artifacts and final audit pass with 319 tests; setup is 234.75 MiB, latest portable is 315.89 MiB, all artifacts are below 400 MiB, staged sources match, portable CLI exits 0, and no large speech model is bundled; all iteration steps are 100% complete |
| 2026-06-13 | Minimum distinct-case reliability artifact rebuild | Setup and portable artifact rebuild succeeded; verification/rebuild/docs is 75% complete pending final acceptance checks and evidence refresh |
| 2026-06-13 | Full source verification before minimum distinct-case rebuild | Full suite passes with 319 tests; embedded-runtime compilation and diff checks pass; verification/rebuild/docs is 50% complete |
| 2026-06-13 | Minimum distinct-case reliability gate implementation | Representative coverage now requires existing source-video paths and at least 10 distinct videos each for Marathi, Hindi, and Indian English; all 16 dataset evaluator tests pass; broader verification in progress |
| 2026-06-13 | Minimum distinct-case reliability regression verified red | Thirty otherwise-perfect manifest rows that reuse one source video per language still have no distinct-case coverage result and can satisfy the existing representative gate; implementation in progress |
| 2026-06-13 | Started minimum distinct-case reliability evaluation | No representative media or labels exist in the repository, and the current 95% dataset gate can pass with only one case per target language; regression fix in progress |
| 2026-06-13 | Human-reference transcription accuracy gate and artifact audit | Dataset success now requires at least 95% Unicode-aware transcript word accuracy per case, overall, and independently per target language; rebuilt artifacts and final audit pass with 318 tests; setup is 234.75 MiB, latest portable is 315.89 MiB, all artifacts are below 400 MiB, staged sources match, portable CLI exits 0, and no large speech model is bundled; all iteration steps are 100% complete |
| 2026-06-13 | Human-reference transcription artifact rebuild | Setup and portable artifact rebuild succeeded; verification/rebuild/docs is 75% complete pending final acceptance checks and evidence refresh |
| 2026-06-13 | Full source verification before human-reference transcription rebuild | Full suite passes with 318 tests; compilation and diff checks pass; verification/rebuild/docs is 50% complete |
| 2026-06-13 | Broader human-reference transcription verification | Accuracy dataset, agreement-output, transcription-provider, and main suites pass with 113 tests; compilation and diff checks pass; verification/rebuild/docs is 25% complete |
| 2026-06-13 | Human-reference transcription accuracy gate implementation | Dataset cases load generated and human-reference transcripts, compute Unicode-aware word error rate, and require at least 95% word accuracy per case, overall, and independently per target language; all 15 dataset tests pass; broader verification in progress |
| 2026-06-13 | Human-reference transcription regression verified red | Otherwise-perfect representative cases still have no transcription_accuracy result or gate when system and reference transcripts are absent; implementation in progress |
| 2026-06-13 | Started human-reference transcription accuracy evaluation | Confirmed the dataset 95% gate can pass without loading a system transcript or comparing it with any human reference transcript; regression fix in progress |
| 2026-06-13 | Human-rated B-roll relevance gate and artifact audit | Dataset success now requires every generated B-roll suggestion to be human-rated and at least 95% relevant overall and independently per target language; rebuilt artifacts and final audit pass with 316 tests; setup is 234.76 MiB, portable is 317.29 MiB, staged sources match, portable CLI exits 0, and no large speech model is bundled; all iteration steps are 100% complete |
| 2026-06-13 | Human-rated B-roll artifact rebuild | Setup and portable artifact rebuild succeeded; verification/rebuild/docs is 75% complete pending final acceptance checks and evidence refresh |
| 2026-06-13 | Full source verification before human-rated B-roll rebuild | Full suite passes with 316 tests; compilation and diff checks pass; verification/rebuild/docs is 50% complete |
| 2026-06-13 | Broader human-rated B-roll verification | Accuracy dataset, agreement-output, and main suites pass with 94 tests; compilation and diff checks pass; verification/rebuild/docs is 25% complete |
| 2026-06-13 | Human-rated B-roll relevance gate implementation | Dataset cases load broll_suggestions.json and match every suggestion one-to-one to valid timestamped human ratings; pooled and per-language relevance must each reach 95%; all 13 dataset tests pass; broader verification in progress |
| 2026-06-13 | Human-rated B-roll regression verified red | Perfect edit agreement, target coverage, duration, and story preservation still have no broll_relevance result or gate when human ratings are absent; implementation in progress |
| 2026-06-13 | Started human-rated B-roll relevance evaluation | Confirmed the dataset 95% gate can pass without loading or measuring broll_suggestions.json or any human relevance ratings; regression fix in progress |
| 2026-06-13 | Actual retained-edit duration gate and artifact audit | Declared 90-second metadata can no longer hide a materially short or long actual edit; rebuilt artifacts and final audit pass with 314 tests; setup is 234.75 MiB, portable is 317.30 MiB, staged sources match, portable CLI exits 0, and no large speech model is bundled; all iteration steps are 100% complete |
| 2026-06-13 | Actual-duration gate artifact rebuild | Setup and portable artifact rebuild succeeded; verification/rebuild/docs is 75% complete pending final acceptance checks and evidence refresh |
| 2026-06-13 | Full source verification before actual-duration gate rebuild | Full suite passes with 314 tests; compilation and diff checks pass; verification/rebuild/docs is 50% complete |
| 2026-06-13 | Broader actual-duration gate verification | Accuracy dataset, agreement-output, main, and output-validation suites pass with 96 tests; compilation and diff checks pass; verification/rebuild/docs is 25% complete |
| 2026-06-13 | Actual retained-edit duration gate implementation | Agreement reports measure unique retained cuts without double-counting, reject invalid actual cuts, and dataset success requires every output to remain within 85%-110% of target duration; all 4 focused checks pass; broader verification in progress |
| 2026-06-13 | Actual retained-duration regressions verified red | Core agreement does not expose unique retained duration and a perfectly matching five-second edit has no dataset duration gate despite a declared 90-second target; implementation in progress |
| 2026-06-13 | Started actual retained-edit duration gate | Confirmed representative coverage validates declared 90-second metadata but not the duration of actual unique retained cut ranges, allowing an equally labelled materially short edit to pass; regression fix in progress |
| 2026-06-13 | Per-language reliability gate and artifact audit | Pooled agreement can no longer hide a required target language below 95%; rebuilt artifacts and final audit pass with 312 tests; setup is 234.76 MiB, portable is 317.29 MiB, staged sources match, portable CLI exits 0, and no large speech model is bundled; all iteration steps are 100% complete |
| 2026-06-13 | Per-language reliability artifact rebuild | Setup and portable artifact rebuild succeeded; verification/rebuild/docs is 75% complete pending final acceptance checks and evidence refresh |
| 2026-06-13 | Full source verification before per-language reliability rebuild | Full suite passes with 312 tests; compilation and diff checks pass; verification/rebuild/docs is 50% complete |
| 2026-06-13 | Broader per-language reliability verification | Accuracy dataset, agreement-output, and main suites pass with 90 tests; compilation and diff checks pass; verification/rebuild/docs is 25% complete |
| 2026-06-13 | Per-language 95% reliability gate implementation | Dataset reports expose per-language agreement, validity, story preservation, and below-target languages; aggregate success now requires every required target language to independently meet 95%; all 10 dataset evaluator tests pass; broader verification in progress |
| 2026-06-13 | Per-language reliability regression verified red | Complete Marathi, Hindi, and Indian English coverage produces pooled agreement above 95% while Hindi remains below 95%, but the report has no language reliability gate and would pass; implementation in progress |
| 2026-06-13 | Started per-language 95% reliability gate | Confirmed pooled dataset agreement can exceed 95% while one required target language remains below 95%, allowing a false reliability claim; regression fix in progress |
| 2026-06-12 | Full-source agreement scoring and artifact audit | Every declared source second is now measured and out-of-source decisions are rejected; rebuilt artifacts and final audit pass with 311 tests; setup is 234.75 MiB, portable is 317.30 MiB, staged sources match, portable CLI exits 0, and no large speech model is bundled; all iteration steps are 100% complete |
| 2026-06-12 | Full-source agreement artifact rebuild | Setup and portable artifact rebuild succeeded; verification/rebuild/docs is 75% complete pending final acceptance checks and evidence refresh |
| 2026-06-12 | Full source verification before full-source agreement rebuild | Full suite passes with 311 tests; compilation and diff checks pass; verification/rebuild/docs is 50% complete |
| 2026-06-12 | Broader full-source agreement verification | Accuracy output, dataset, and main suites pass with 89 tests; compilation and diff checks pass; verification/rebuild/docs is 25% complete |
| 2026-06-12 | Full-source agreement scoring implementation | Dataset cases pass source duration into human-agreement measurement; every declared source second is scored and out-of-source system or human ranges are rejected; all 4 focused regressions pass; broader verification in progress |
| 2026-06-12 | Full-source agreement regressions verified red | Core evaluator rejects source-duration input and dataset case totals only 90 of 240 declared seconds, proving omitted source intervals currently escape measurement; implementation in progress |
| 2026-06-12 | Started full-source human-agreement scoring | Confirmed dataset evaluation excludes intervals omitted by both system decisions and human keep labels even though source duration is available, allowing incomplete timeline measurement and missing pause/dead-air decisions; regression fix in progress |
| 2026-06-12 | Representative dataset-coverage gate and artifact audit | Dataset cannot pass 95% without complete target coverage; rebuilt artifacts and final audit pass with 307 tests; setup is 234.77 MiB, portable is 317.29 MiB, staged sources match, embedded CLI exits 0, and no large speech model is bundled; all iteration steps are 100% complete |
| 2026-06-12 | Representative-coverage artifact rebuild | Setup and portable artifact rebuild succeeded; verification/rebuild/docs is 75% complete pending final acceptance checks and evidence refresh |
| 2026-06-12 | Full source verification before representative-coverage rebuild | Full suite passes with 307 tests; compilation and diff checks pass; verification/rebuild/docs is 50% complete |
| 2026-06-12 | Broader representative-coverage verification | Accuracy dataset, agreement-output, and main suites pass with 85 tests; compilation and diff checks pass; verification/rebuild/docs is 25% complete |
| 2026-06-12 | Representative dataset-coverage gate implementation | Dataset reports now expose coverage metadata and cannot pass the 95% gate without valid 3-7 minute, 9:16, 90-second Marathi, Hindi, and Indian English cases; focused pass/fail coverage regressions pass; broader verification and rebuild in progress |
| 2026-06-12 | Started representative dataset-coverage gate | Confirmed a single perfect short case can currently make the dataset report that the 95% target is met without covering 3-7 minute 9:16, 90-second Marathi, Hindi, and Indian English target inputs; regression fix in progress |
| 2026-06-12 | Under-minimum duration safeguard and artifact audit | Duration enforcement preserves an over-budget story when every whole-segment or whole-word removal would violate the accepted 85% minimum; rebuilt artifacts and final audit pass with 305 tests; setup is 234.75 MiB, portable is 317.29 MiB, staged sources match, embedded CLI exits 0, and no large speech model is bundled; all iteration steps are 100% complete |
| 2026-06-12 | Under-minimum safeguard artifact rebuild | Setup and portable artifact rebuild succeeded; final verification/rebuild/docs step is 75% complete pending acceptance checks and final documentation evidence |
| 2026-06-12 | Full source verification before under-minimum safeguard rebuild | Full suite passes with 305 tests; compilation and diff checks pass; final verification/rebuild/docs step is 50% complete |
| 2026-06-12 | Broader under-minimum safeguard verification | Affected analysis, main, accuracy-output, and validation suites pass with 133 tests; compilation and diff checks pass; final verification/rebuild/docs step is 25% complete |
| 2026-06-12 | Under-minimum duration safeguard implementation | Duration enforcement now stops when every whole-segment or whole-word removal would push the story below the accepted 85% minimum; all 8 focused duration-budget tests pass; broader verification and rebuild in progress |
| 2026-06-12 | Added per-step progress percentages | Every project Markdown status section now shows the completion percentage for each active iteration step so future sessions can resume without reconstructing progress |
| 2026-06-12 | Started under-minimum duration-enforcement safeguard | Confirmed an over-budget edit can be shortened below the accepted 85% minimum when no whole-segment removal preserves the range, producing a worse and less complete story; regression fix in progress |
| 2026-06-12 | Post-clamp minimum-duration safeguard and artifact audit | Selected ranges are revalidated after boundary normalization, preventing source-end clamping from producing sub-0.5-second micro-cuts; rebuilt artifacts and final audit pass with 304 tests; setup is 234.75 MiB, portable is 317.30 MiB, staged sources match, embedded CLI exits 0, and no large speech model is bundled |
| 2026-06-12 | Full source verification before post-clamp artifact rebuild | Full suite passed with 304 tests; compilation and diff checks passed before the successful artifact rebuild |
| 2026-06-12 | Post-clamp minimum-duration safeguard | Selected ranges are revalidated after boundary normalization, preventing source-end clamping from producing sub-0.5-second micro-cuts; affected analysis, main, accuracy-output, and validation suites passed with 132 tests |
| 2026-06-12 | Started post-clamp minimum-duration safeguard | Confirmed a selected range can pass the 0.5-second minimum check and then be clamped at the source end into an unnatural sub-0.5-second micro-cut; regression fix in progress |
| 2026-06-12 | Added persistent goal-progress estimate | Every project Markdown status section now reports 85% estimated implementation completion, 15% remaining, and that measured progress toward 95% agreement is unavailable until representative human-labelled evaluation |
| 2026-06-12 | Claude-response timestamp-integrity safeguards and artifact audit | Negative, NaN, and infinite selected timestamps are rejected before downstream cut handling; rebuilt artifacts and final audit pass with 303 tests; setup is 234.76 MiB, portable is 317.30 MiB, staged sources match, embedded CLI exits 0, and no large speech model is bundled |
| 2026-06-12 | Full source verification before Claude-timestamp artifact rebuild | Full suite passed with 303 tests; compilation and diff checks passed before the successful artifact rebuild |
| 2026-06-12 | Claude-response timestamp-integrity safeguards | Negative, NaN, and infinite selected timestamps are rejected before downstream cut handling; affected analysis, main, accuracy-output, and validation suites passed with 131 tests |
| 2026-06-12 | Started Claude-response timestamp-integrity safeguards | Confirmed selected ranges are not explicitly rejected when start/end timestamps are negative or non-finite, allowing invalid source cuts into downstream processing; regression fix in progress |
| 2026-06-12 | Sarvam monotonic-timestamp protection and artifact audit | Backward start/end entries are filtered while surrounding valid speech remains; rebuilt artifacts and final audit pass with 299 tests; setup is 234.75 MiB, portable is 317.29 MiB, staged sources match, embedded CLI exits 0, and no large speech model is bundled |
| 2026-06-12 | Full source verification before monotonic-timestamp artifact rebuild | Full suite passed with 299 tests; compilation and diff checks passed before the successful artifact rebuild |
| 2026-06-12 | Sarvam monotonic-timestamp protection | Backward start/end entries are filtered while surrounding valid speech remains; focused transcription, filler, caption, and accuracy suites passed with 167 tests |
| 2026-06-12 | Started Sarvam monotonic-timestamp protection | Confirmed individually valid word ranges are still accepted when their start or end moves backward relative to the previous word, allowing malformed chronological cut data; regression fix in progress |
| 2026-06-12 | Sarvam timestamp-integrity safeguards | Blank and invalid Sarvam word timestamp entries are filtered before segmentation, preventing leading-silence boundary shifts and invalid word-level cuts; rebuilt artifacts and final audit pass with 297 tests |
| 2026-06-12 | Started Sarvam timestamp-integrity safeguards | Confirmed blank timestamp tokens can shift a valid spoken segment into leading silence and non-positive word ranges are accepted into downstream cut-boundary data; regression fix in progress |
| 2026-06-12 | Sarvam short-pause segmentation alignment | Sarvam word-timestamped utterances now split after pauses over 0.5 seconds, matching pause removal and improving editorial/cut-boundary granularity while exact 0.5-second pauses remain contiguous; rebuilt artifacts and final audit pass with 295 tests |
| 2026-06-12 | Started Sarvam short-pause segmentation alignment | Confirmed Sarvam utterance segmentation still uses a 0.75-second boundary, so a removable 0.6-second gap remains inside one editorial segment despite the project-wide 0.5-second pause threshold; regression fix in progress |
| 2026-06-12 | Anaphoric-fragment story protection | Predicate-aware context scoring prevents fallback selection of unsupported anaphoric fragments such as "This helps..." while preserving explicit demonstrative noun phrases such as "This video..."; rebuilt artifacts and final audit pass with 293 tests |
| 2026-06-12 | Started anaphoric-fragment story protection | Confirmed fragments such as "This helps patients understand IVF treatment" are scored as context-independent and can be selected without the premise that defines "this"; regression fix in progress |
| 2026-06-12 | Common contraction meaning protection | Editorial repetition scoring and word-level false-start detection now preserve corrected claims using common omitted English negation contractions; rebuilt artifacts and final audit pass with 290 tests |
| 2026-06-12 | Started common contraction meaning protection | Confirmed negation detection omits common forms such as "didn't", "hasn't", "shouldn't", and "couldn't", allowing corrected claims to be treated as duplicate takes; regression fix in progress |
| 2026-06-12 | Comma-conjoined B-roll negation scoping | Separate affirmative clauses introduced by comma-plus-"and" with an explicit subject retain mapped service visuals, while negated comma-separated service lists remain neutral; rebuilt artifacts and final audit pass with 288 tests |
| 2026-06-12 | Started comma-conjoined B-roll negation scoping | Identified that a separate affirmative clause such as "We do not rush patients, and we provide IVF treatment" is still treated as wholly negated; regression fix in progress while preserving negated comma-separated service lists |
| 2026-06-12 | Canonicalized same-decision human labels | Overlapping or touching same-decision annotations merge into one continuous interval before keep/remove and boundary scoring, while conflicting overlaps remain invalid; rebuilt artifacts and final audit pass with 271 tests |
| 2026-06-12 | Rejected contradictory system decisions | Agreement reports now expose system validity, contradictory overlapping output receives zero agreement, and dataset reports count invalid system cases; rebuilt artifacts and final audit pass with 273 tests |
| 2026-06-12 | Protected semantic opposites from repetition removal | Editorial scoring and word-level false-start detection preserve one-sided high-confidence antonym contrasts while still removing true duplicates containing both terms; rebuilt artifacts and final audit pass with 277 tests |
| 2026-06-12 | Protected numeric claims from repetition removal | Editorial scoring and word-level false-start detection preserve statements with materially different explicit digits or number words while still removing identical numeric repeats; rebuilt artifacts and final audit pass with 281 tests |
| 2026-06-12 | Protected Marathi/Hindi written quantities | Editorial scoring and word-level false-start detection preserve materially different common Devanagari quantity words while retaining identical-quantity duplicate detection; rebuilt artifacts and final audit pass with 285 tests |
| 2026-06-12 | Scoped B-roll negation handling | Relevant affirmative concept clauses retain mapped B-roll suggestions even when another clause is negative, while directly negated IVF services still use neutral limitation visuals; rebuilt artifacts and final audit pass with 286 tests |
| 2026-06-12 | Started scoped B-roll negation handling | Confirmed any negation token currently switches the entire suggestion to limitations mode, even when a separate clause affirmatively states the relevant IVF service; regression fix in progress |
| 2026-06-12 | Started Marathi/Hindi quantity protection | Confirmed Marathi पाच-दिवस versus दहा-दिवस claims are scored as exact duplicates and can lose the corrected duration; regression fix in progress |
| 2026-06-12 | Started numeric-claim repetition protection | Confirmed 30-percent versus 70-percent claims are scored as exact duplicates and five-day versus ten-day claims receive a 0.714 repetition score; regression fix in progress |
| 2026-06-12 | Started semantic-opposite repetition protection | Confirmed highly similar opposite claims such as safe/unsafe, increases/decreases, and before/after receive 0.71-0.75 repetition scores and can be removed as false starts; regression fix in progress |
| 2026-06-12 | Started contradictory system-decision validation | Confirmed overlapping system keep/remove rows can currently receive perfect agreement and pass the 95% gate; regression fix in progress |
| 2026-06-12 | Started overlapping human-label canonicalization | Confirmed overlapping human keep labels are accepted but counted as multiple edits, inflating boundary totals for one continuous kept range; regression fix in progress |
| 2026-06-12 | Protected semantic sentence-start words | Ambiguous words `right`, `well`, and `now` are removed only with a comma-delimited discourse cue; semantic timing/location phrases remain intact; rebuilt artifacts and final audit pass with 270 tests |
| 2026-06-12 | Started semantic sentence-start filler fix | Confirmed ambiguous words such as "right" and "now" are removed unconditionally at sentence starts, which can change meaning and create awkward cuts; regression fix in progress |
| 2026-06-12 | Corrected individual cut-boundary measurement | Human agreement scores starts and ends separately with type-safe one-to-one matching, so one correct edge receives partial credit; rebuilt artifacts and final audit pass with 268 tests |
| 2026-06-12 | Started individual cut-boundary measurement fix | Confirmed the evaluator gives zero boundary credit when one edge of a kept range is correct and the other is wrong, despite start and end being separate cut decisions; regression fix in progress |
| 2026-06-12 | Preserved context across rejected filler | Refinement, story fill, and duration trimming use the nearest substantive antecedent while skipping rows rejected by the editorial gate; rebuilt artifacts and final audit pass with 267 tests |
| 2026-06-12 | Started skipped-filler context preservation fix | Confirmed refinement, fill, and duration trimming require only the immediately previous transcript row, which can orphan a valid conclusion when rejected filler or a weak aside intervenes; regression fix in progress |
| 2026-06-12 | Protected transitive-only distinct statements | Duplicate preference penalizes only takes directly similar to the preferred retained take; rebuilt artifacts and final audit pass with 264 tests |
| 2026-06-12 | Started transitive-duplicate accuracy fix | Confirmed a statement with no direct similarity to the preferred take can receive a default 0.55 repetition penalty solely through an intermediate take; regression fix in progress |
| 2026-06-11 | Improved editorial lexical precision | Whole-word scoring rejects embedded signal substrings such as "how" in "showcase" and "care" in "scared"; rebuilt artifacts and final audit pass with 263 tests |
| 2026-06-11 | Started editorial lexical-precision audit | Found substring matching can falsely treat words such as "showcase" as hook term "how" and "scared" as emotional term "care"; regression fix in progress |
| 2026-06-11 | Clarified staged model-asset audit | Confirmed no large speech-model bundle; documented the dependency-owned 1.19 MiB Silero VAD asset and tiny ONNX Runtime samples |
| 2026-06-11 | Rejected under-length final exports | Output validation now requires the same 85%-110% duration range as story accuracy reporting; rebuilt artifacts and final audit pass with 262 tests |
| 2026-06-11 | Added persistent project-status documentation | Created this authoritative ledger; verified that every project Markdown file contains a status section and links here |
| 2026-06-11 | Improved B-roll grounding | Suggestions use retained words and exact timestamps; negated statements use neutral visuals; 261 tests pass |
| 2026-06-11 | Protected corrective contrasts | Negated and contracted statements are not removed as duplicate takes |
| 2026-06-11 | Improved subtitle accuracy | Partially cut words are excluded from SRT output |
| 2026-06-11 | Preserved story dependencies | Fill and duration trimming keep supported conclusions with required premises |
| 2026-06-11 | Improved render accuracy | Natural contiguous cuts, audio fades/resampling, and A/V drift validation added |
| 2026-06-11 | Added strict agreement measurement | Duration-weighted balanced evaluator and mandatory story-meaning assessment added |
