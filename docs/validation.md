# Interview Studio — 2026-09-30

- Added named candle/female/male avatars, five fallback genres, multiple template selection, saved Style Lab script search with role selection, and immutable downloadable configuration Markdown identified by use-case/avatar IDs.
- Added separate `biographer_interviews` PostgreSQL database with independent `i0001` migration, source chunks, durable session/turn records, original recordings and reviewed/approved snapshots. The live PostgreSQL fixture verifies creation, approval, indexed full-text search and deletion within a rolled-back transaction.
- Added text and turn-based voice chat, synthetic-microphone recording, amplitude-driven flame animation, saved speech replies, failure recovery, correction/approval/export and approved-script retrieval. Configuration copies preserve source provenance; source participant facts are explicitly separated from the new interviewee.
- Validation: **65 backend tests and all 4 Chrome acceptance tests passed**, including foundation, Style Lab, processing controls and Interview Studio. Python lint/format, strict TypeScript and production builds passed. Backend tests use mocked Gemini responses, real FFmpeg conversion and real local PostgreSQL/storage/Temporal integration where marked. Browser acceptance uses real account/configuration/session creation, synthetic Chrome microphone input, and deterministic fixtures for provider-dependent conversation/review responses. The separate backend approval tests exercise actual persistence.
- Live Gemini conversation/transcription/TTS quality, physical microphone input, and Safari are not verified. Voice is per-turn (two minutes maximum), retrieval is lexical, and generation sees only the latest 40 turns plus references; all saved turns remain available for review/export. Screenplay generation remains a later phase.

# Delete processing and corresponding scripts — 2026-09-29

- Stopped, failed/interrupted and completed transcription cards expose **Delete processing & script**. The review page exposes **Delete script**, including scripts without a recent job card. Confirmation names the recording and explains dependent-data deletion and local-file retention.
- Owner-authorized deletion is serialized under the profile lock and blocked while processing is active/stopping. It removes the working transcript, approved archives and cascading memory rows, dependent patterns/published versions, source transcription jobs and profile analysis checkpoints. It retains the source recording and resets review state so fresh transcription can start.
- Analysis-job deletion removes its job/checkpoint while retaining existing scripts/patterns. Exported local TXT/JSON files are outside this deletion and remain untouched.
- Ruff, TypeScript and production builds passed. Full backend suite: **56 passed**, including live storage/Temporal checks. New tests cover failed/cancelled/completed job deletion, owner isolation, archive/memory/publication cleanup, retained media, fresh transcription, stopping guards and manually authored script deletion.
- Both Chrome checks passed: real-stack script deletion after archive/publication (cancel and confirm, empty history/search, retained recording), and processing-card deletion confirmation with recording retention. Only synthetic test data was deleted. Final UI refinement also allows clearing old processing history when its job has fallen outside the latest-job list.

# Remove recording upload size cap — 2026-09-28

- Removed the browser/API 2 GiB cap for audio and video, including the old upload hint. Nonempty files, supported types, actual-content validation and the four-hour duration bound remain enforced. Images/documents retain their existing limits.
- Multipart chunk size grows beyond the old fixed-size plan to stay within 10,000 parts. API start/resume, browser slicing and completion validation use the same derived size. Existing <=2 GiB chunk boundaries are unchanged. Completion manifests have a narrowly scoped 2 MiB proxy allowance; other JSON requests retain 256 KiB.
- Storage protocol bounds are still checked before beginning uploads. Available MinIO disk space, temporary processing space and provider-specific limits remain practical constraints. Reference: [S3 multipart protocol limits](https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html).
- Ruff, TypeScript, production builds and **52 backend tests passed**, including live storage/Temporal checks. Added size-only tests for >2 GiB recordings, adaptive boundaries, a simulated 100 GiB start/resume and protocol-cap rejection.
- Chrome foundation check passed, including a simulated 3 GiB recording reaching upload initiation. Only file metadata was simulated; the upload response was intercepted. No multi-gigabyte file was transferred or transcribed as part of verification.

# Recording-wide speaker panel and inline menus — 2026-09-28

- One top panel lists base speaker labels from all sections/pages. Assignments save immediately across section prefixes (for example `1: Speaker A` and `2: A`), preserving explicit local overrides. Each sentence has an adjacent role dropdown that immediately saves a local override.
- The panel reports remaining unassigned sentences, local override counts and missing required roles. This resolves the previous need to discover unassigned speakers separately on each transcript page. Section labels are grouped defaults, not verified identities; the UI explains local corrections for label reuse.
- Ruff, TypeScript, production builds and all **50 backend tests passed**. A new cross-section test assigns A/B, preserves an overridden sentence, and successfully approves the transcript. Owner isolation remains tested.
- **2 Chrome checks passed**: the real-stack review/archive/style workflow including the single top panel and inline changes, plus processing controls. The mobile review screenshot was inspected with no horizontal overflow. Only synthetic transcripts were changed for validation.

# Speaker role defaults and local overrides — 2026-09-28

- Selecting a role in the turn editor applies it on save to matching exact speaker labels throughout the current recording. The default checkbox can be unchecked to create a persistent local override; later bulk/default changes preserve these exceptions. Text-only edits do not propagate roles. Different section-prefixed labels are not automatically treated as the same person.
- Alembic `0005` adds `transcript_turns.role_override`, false for existing turns. API, worker and web were rebuilt and restarted successfully.
- Ruff, TypeScript and full backend suite: **49 passed**, including storage/Temporal integration. New regression checks cover 53 matching turns spanning pagination, distinct section labels, local override persistence, bulk changes, and returning an override to the shared role.
- Chrome Style Lab and processing regressions: **2 passed**. The real-stack browser check verifies the default checkbox, propagation to another turn, an individual exception preserved by subsequent propagation, and the existing archive/publication flow. No personal transcript was edited for testing.

# Duplicate-upload reminders — 2026-09-28

- Matching uses the same uploader's historical audit records, case-insensitive filename and exact byte size, limited to projects they can still access. Same-request multipart resumes are excluded; explicit override permits necessary copies. No content hash claim or renamed-file detection.
- Ruff, TypeScript and production API/worker/web builds passed. Full backend suite: **48 passed**, including live storage/Temporal checks.
- Chrome foundation and Style Lab checks: **2 passed**. A repeated synthetic image upload triggered the reminder; cancel left the count unchanged, and accept created a second processed copy. Synthetic projects/materials were cleaned up.
- No database migration or external provider call is needed for this reminder.

# Script review, local archive, and conversation memory — 2026-09-28

- Dedicated `/style-lab/{profile}/scripts/{source}` page with editing, playback, immutable version history, folder-save recovery, and cited keyword search.
- Production API/web builds, strict TypeScript, and Alembic `0004` migration passed. Local API/worker/web restarted successfully.
- Ruff and full backend suite: **47 passed**, including live MinIO/Temporal integration. New archive cases cover role validation, stale revision rejection, immutable history, checksum mismatch, idempotent acknowledgement/indexing, latest-saved-version search, owner isolation, source retention, and profile deletion cascades.
- Chrome processing-control regression passed. Extended real-stack Style Lab test passed: cancel picker, fail disk write, reload unindexed archive, retry save, verify exported TXT/JSON, search PostgreSQL, view snapshot, then publish style and preserve frozen evidence after correction.
- Browser folder picker/file handles are simulated in automation. Native macOS folder permissions and an actual user-selected disk write remain manual verification. No user interview was sent to Gemini or exported for these tests.
- The 390px review-page screenshot was inspected; no horizontal overflow. Synthetic project/profile/media cleanup passed. Cloud migration is documented, not deployed; semantic embeddings and future session-memory tables remain planned.

# Recording deletion and transcription stop controls — 2026-09-27

- API, worker, and web production rebuild passed; TypeScript passed.
- Ruff and full backend suite passed: **45 tests**, including live storage/Temporal acceptance.
- Both targeted Chrome checks passed: existing Style Lab review/publication and processing controls (stop, stopping, stopped, resume, deletion confirmation cancellation/acceptance, and refreshed lists).
- New backend cases cover owner-only stopping/deletion, retained checkpoints, queued work never invoking a provider after stop, cancellation of an in-flight simulated HTTP request, discarded late results, original/transcript/draft cleanup, and published-evidence protection.
- Cancellation tests use synthetic providers/HTTP clients. Closing the local connection cannot guarantee termination of processing or billing for a request already accepted by Google.
- No personal recording was deleted or explicitly stopped for these tests. The existing local services were restarted to deploy the controls.

# Gemini request fix — 2026-09-27

The configured `gemini-3.1-pro-preview` returned HTTP 400 / INVALID_ARGUMENT for the original transcript schema. Isolated live probes succeeded for plain text, audio without a schema, and audio with a minimal schema; a text-only request with the original transcript schema reproduced the rejection. No personal video was used for these diagnostic probes.

The provider now resolves schema references and sends a small structural schema (types, fields, required fields, enums, additional-property rules). Full Pydantic length/count/range/timestamp checks remain in the application after generation. The fixed audio request returned HTTP 200, STOP, and a validated transcript response. HTTP failures now distinguish invalid requests, authentication, permissions, unavailable models, and quota limits without echoing arbitrary provider error text.

Ruff and the full backend suite passed: **39 tests**, including real MinIO/Temporal integration. The API and worker were rebuilt and the latest failed 48-section transcription was requeued through the existing retry service. Its first three sections were saved successfully with no current error (3/48 at the status check); the rest continued in the background. This validates request compatibility, not overall transcript accuracy or style fidelity.

# Processing flow validation — 2026-09-21

- Web production rebuild and TypeScript checks passed.
- Both targeted Chrome checks passed: the existing real-stack Style Lab review/publication workflow and a new processing-flow regression check.
- The new check uses explicitly mocked provider/job responses to verify the uploaded-recording start button, missing-configuration explanation, authorization gate, automatic attachment before transcription, 50% progress, reload recovery, persistent 100% completion, Open transcript navigation, and mobile overflow.
- Live Gemini processing remains unverified: GEMINI_API_KEY and GEMINI_MODEL are still unset. File preparation uses an indeterminate indicator because the media worker does not report a reliable percentage; transcription reports completed audio sections.

# Style Lab validation — 2026-09-20

- Production Docker rebuild and Alembic `0003` migration: passed; API healthy after recreation, worker started without logged errors.
- Strict TypeScript: passed.
- Ruff: passed with `ruff check --no-cache .`.
- Full backend suite with `RUN_LIVE=1` and `STORAGE_CONNECT_HOST=minio`: **37 passed**, no skipped live test. This includes the existing five-format upload/download acceptance test through MinIO and Temporal.
- Both Chrome acceptance checks passed on the final application build: biography foundation and the new Style Lab workflow. The Style Lab test passed after its selectors were changed to use accessible roles for populated controls. Both tests check mobile layouts and browser JavaScript errors.

Style Lab coverage includes private profile access, cross-profile evidence rejection, speaker and timestamp validation, source retention, idempotent jobs/publication, approval gates, correction invalidation, frozen snapshots, section-wide speaker-role assignment, sanitized failures, and provider request structure. A real FFmpeg 65-second audio fixture tests three segments, forced interruption, checkpoint resumption, global timestamps, and neutral speaker labels. Four-hour segment planning is also tested; this is not a four-hour real-speech quality test.

The Style Lab browser test uploads a synthetic WAV through the running stack, loads its audio proxy, enters two clearly synthetic transcript turns, reviews them, approves a pattern, publishes version 1, edits the current transcript, and verifies that the published evidence stays unchanged. Desktop and 390-pixel screenshots were inspected. Synthetic profiles, projects, and media from successful and interrupted runs were removed; synthetic accounts remain as in the existing test suite.

**Not live-verified:** Gemini transcription/extraction quality, speaker identification on real interviews, multi-hour processing under real provider quota, or style fidelity. Neither `GEMINI_API_KEY` nor `GEMINI_MODEL` is configured in the current server environment. Model responses in automated tests are explicit fixtures, not evidence of model quality. See [Style Lab](style-lab.md) for setup and implementation limits. Reference-question import, session orchestration, practice interviews, and coverage reports remain pending the user's reference list and subsequent milestones.

The historical foundation result follows for context.

---

# Foundation validation — 2026-09-15

Validated locally on Apple silicon with Docker Desktop running native ARM containers.

## Results

- Next.js production Docker build: passed (strict TypeScript compilation included).
- Standalone TypeScript check: passed.
- Ruff: passed using `ruff check --no-cache .` inside the non-root application container.
- Full backend suite: **23 passed**. This includes a real Compose-stack acceptance test; no live test was skipped in the final run.
- Headless Chrome acceptance: **1 passed**, including desktop and 390-pixel mobile layout checks, with no browser JavaScript errors.
- All seven runtime services running: web, API, worker, PostgreSQL, Redis, MinIO, and Temporal. API, PostgreSQL, and Redis health checks passed.

## Exercised behavior

Accounts, session revocation, project CRUD, role enforcement, project isolation, audit history, upload ownership, MIME/name/size rejection, idempotency keys, repeat completion, completion recovery after storage success, worker replay idempotency, and terminal invalid-media failures.

The real stack test uploaded synthetic JPG, MP4, MP3, DOCX, and a 9 MB TXT file. The TXT upload crossed the part boundary and verified resume information after the first part. Every asset reached ready through Temporal processing. Image/video thumbnails and video/audio proxies were produced. Downloaded originals matched their recorded SHA-256 checksums. The test removed its files and project.

The browser created an account and biography, uploaded and previewed a JPEG, uploaded a text memory, saved a note, reloaded to confirm persistence, checked mobile overflow, verified the public session response omitted the API token, and deleted its test project and media. An initial cleanup timing bug in the test was corrected by waiting for project navigation; the final run passed. The leftover synthetic project from that earlier run was removed separately.

## Not claimed as verified

Google AI integrations, transcription, screenplay generation, video generation, final film rendering, production deployment, email recovery/MFA, a native GCS adapter, and the optional live ClamAV service are outside this foundation validation. Scanning remains explicitly disabled in the default development configuration. See architecture.md for operational limits.

Two upstream Starlette/AnyIO deprecation warnings appear in pytest output; they do not fail the checks.
