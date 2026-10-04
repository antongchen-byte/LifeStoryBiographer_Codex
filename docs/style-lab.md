# Style Lab

Style Lab develops **how to interview** from recordings. The user's reference-question list is pending; question import, coverage tracking, practice interviews, and a combined interview configuration are deliberately not populated by this milestone. The supplied interview architecture is archived in [interview-application-specification.md](interview-application-specification.md).

## Use it

1. Open `/style-lab` and create an interviewer profile in a biography you own.
2. Upload audio/video with the resumable media uploader. File preparation has a waiting indicator. Choose **Create transcript** beside the prepared recording; this adds it to your profile and queues transcription in one action. The authorization checkbox and any missing Gemini configuration are shown next to the workflow.
3. Follow the transcription progress bar and saved-section count, which survive page reloads. When processing finishes, choose **Open transcript** on the completion card or recording card. You can also open **Transcript workspace** to enter an existing transcript manually with timestamps. Listen to the recording, correct the words, and identify every speaker's role. Approve the transcript when checked.
4. Approve all source transcripts and choose Extract style. Alternatively, select transcript turns, choose Create pattern from selection, and write a rule and example yourself.
5. Review supporting exchanges, refine the generic instruction/example, and explicitly confirm anonymization and observable behavior before approving a pattern.
6. Publish a private style version. Only approved patterns are copied into the immutable snapshot, together with their timestamped evidence. Subsequent edits to a source transcript clear its review and reset affected pattern approvals; existing published snapshots retain the original reviewed evidence.

Published versions are private, and there is no shared-example library in this release. Pattern approval is a human judgment: an instruction to ignore uploaded prompt injections is not a guarantee of model resistance, and confidence is not a measured probability of correctness. Review actual evidence before publishing.

## Enable AI processing

Add these server settings to the root `.env`, then recreate the API and worker:

```dotenv
GEMINI_API_KEY=your-key
GEMINI_MODEL=your-enabled-audio-and-structured-output-model
```

```sh
docker compose up -d --force-recreate api worker
```

Use a Gemini model available to your account that supports audio input and JSON-schema output. There is intentionally no preview-model default that could become unavailable. Credentials stay in the server environment. The browser displays configuration availability only; it never receives the key. A per-profile checkbox makes sending recordings/transcripts to Gemini explicit before jobs are queued. Previously authorized failed jobs can be resumed.

The adapter uses Google's documented [GenerateContent REST endpoint](https://ai.google.dev/api/generate-content), [audio input](https://ai.google.dev/gemini-api/docs/generate-content/audio), and [structured output](https://ai.google.dev/gemini-api/docs/generate-content/structured-output). The wire schema is simplified for Gemini compatibility; Pydantic retains full response validation, and application checks restrict evidence to supplied transcript IDs from this profile. A missing key, provider error, blocked response, invalid schema, or unsupported evidence is surfaced as a job failure; the app does not substitute fabricated transcripts or patterns.

## VocalExtract-Pro adaptation

Reviewed repository: [antongchen-byte/VocalExtract-Pro](https://github.com/antongchen-byte/VocalExtract-Pro), commit `4a38e56e3be937eec4a7e9bd512f097b2fafbd99`.

Relevant files are `src/App.tsx`, `src/lib/videoProcessor.ts`, and `src/lib/gemini.ts`. Its actual processing loop uses **30-second** segments, despite UI copy saying one minute. Its useful design is sequential seek/extract/transcribe, releasing temporary output and reporting progress after each segment.

This project implements that algorithm independently in Python/FFmpeg on the server; it does not vendor the browser application's code. Changes for the biography workflow:

- Download the protected original once per attempt, seek to each segment, and produce one small mono 16 kHz/64 kbps MP3 at a time. The last partial segment is included. Recording uploads have no application-level size cap; storage capacity/protocol limits apply. Existing duration validation still bounds recordings to four hours.
- Persist turns and completed-segment count in one database transaction. Temporal retries resume at the first unsaved segment, with row-lock/generation checks preventing stale attempts from committing duplicate progress. Temporary files are cleaned up by context managers.
- Convert model-relative timestamps to full-recording milliseconds and reject out-of-segment timing.
- Use neutral, section-local speaker labels. Do not infer the interviewer from gender (the reference application did); require human role review. Section boundaries may split speech, so transcription fidelity and speaker consistency need human verification.
- Extract observations from bounded batches of reviewed turns, then compare candidates across recordings using hierarchical consolidation. Evidence IDs are checked after extraction and after each consolidation. Suggestions start pending.

Transcription is a durable database job dispatched through Temporal, not work attached to an HTTP request. One active job per profile prevents concurrent draft edits. Automatic retries preserve chunk/batch checkpoints. An explicit retry of failed analysis clears its candidates because a human may have changed source transcripts since failure. HTTP error bodies and uploaded text are not copied to worker logs or workflow exceptions.

## Data and API

The new migration `0003` adds interviewer profiles, source references, transcript turns, patterns, style versions, and style jobs. Files continue to live in the existing protected media store. Profiles belong to their creator and a biography they own; project collaborators do not inherit access to private style drafts. Deleting media used by a profile is blocked before object removal. Deleting a profile through the owner-only API removes its drafts, versions, jobs, and transcript records, releasing its media references; it does not delete the original recordings.

Endpoints (under `/api`):

- `GET/POST /profiles`, `GET/DELETE /profiles/{id}`
- `POST /profiles/{id}/assets`
- `GET/POST /profiles/{id}/sources/{source}/turns` (reads paginated)
- `PATCH /profiles/{id}/sources/{source}/turns/{turn}`
- `PATCH /profiles/{id}/sources/{source}/speakers` (apply a verified role to a section-local label)
- `POST /profiles/{id}/sources/{source}/review`
- `POST /profiles/{id}/sources/{source}/transcribe`
- `POST /profiles/{id}/analyze`
- `GET /jobs/{id}`, `POST /jobs/{id}/retry`
- `POST /profiles/{id}/patterns`, `PATCH /profiles/{id}/style-drafts/{pattern}`
- `GET /profiles/{id}/patterns/{pattern}/evidence`
- `POST /profiles/{id}/versions`, `GET /profiles/{id}/versions/{version}`

Job creation and publication accept stable request IDs for idempotency. Mutations serialize on the profile row. Published style versions are not complete interview configurations: the reference-question plan and session engine remain future work.

## Validation boundaries

Unit/API tests exercise isolation, review gates, timestamp bounds, original retention, immutable snapshots, evidence validation, idempotent jobs, and corrections. A real 65-second FFmpeg fixture exercises all three segments, a forced provider interruption, resumption, global timestamps, and mandatory neutral roles. The transcription and extraction providers in those tests are explicitly synthetic fixtures.

The browser acceptance test uploads a synthetic WAV through MinIO/Temporal, reviews manually entered fixture exchanges, creates and approves an evidence-backed rule, publishes it, corrects the working transcript, and confirms the old snapshot is unchanged. It checks a 390-pixel layout and cleans up its synthetic profile and media.

Live Gemini request compatibility was verified on 2026-09-27, including successful saved sections from a resumed recording after the schema fix. Full-recording transcription accuracy, multi-hour speech quality, and real-interview style fidelity remain unvalidated. No claim is made that mock-provider results establish model quality. The question/session evaluation plan in `tests/evals/interview-release-plan.json` records pending release cases; it is not a passing evaluation report.

## Stop and delete controls

Each active job has **Stop processing**. Queued work stops immediately; running work enters **Stopping** until the worker acknowledges it. The worker checks durable job state before requests and while awaiting Gemini, closes the local HTTP request, and discards late results. Google may still complete or charge for a request it already accepted. Saved sections remain available through **Open transcript**, and **Resume processing** continues transcription from the checkpoint. Style-analysis retries rebuild their draft candidates from current reviewed transcripts. Finish transcription before approving or editing a partial transcript.

**Delete recording** appears beside attached recordings and uploaded audio/video waiting to be attached. A confirmation explains the permanent removal of the original, previews, transcript, and dependent draft patterns. Stop active processing first and wait for the stopped state. Recordings used by another profile or cited in a published style are protected, with an explanatory error. Uploads still undergoing media preparation must finish before deletion.

API additions: `POST /api/jobs/{id}/stop` and `DELETE /api/profiles/{profile}/sources/{source}`. No new database migration is required; job state is stored as a string. Stopped jobs use `cancelled`, with `stopping` as the worker acknowledgement state. Resume uses the existing retry endpoint and increments the execution generation.
