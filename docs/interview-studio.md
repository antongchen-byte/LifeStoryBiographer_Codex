# Interview Studio

Interview Studio creates an AI interviewer and records new interviews separately from the Style Lab reference library. Open `/interview-studio` from the sidebar after signing in. You must own the selected biography workspace.

## Configure and start

1. Select the biography, then **Ember** (candle), **Maya** (female illustration), or **Eli** (male illustration). Keep the suggested name or enter your own.
Ember defaults to calm and reflective, Maya to warm and curious, and Eli to thoughtful and focused. These are individual character choices, not gender-based traits. The selected personality is saved in the configuration Markdown and used alongside genre and references in conversation prompts. Renaming an avatar retains its personality. Existing saved configurations keep their previous behavior; save a new configuration to adopt the new defaults.

2. Select a genre: life story, oral history, reflective, documentary, or career. This provides the default approach even without reference files.
3. Optionally upload multiple TXT, Markdown, PDF, or DOCX templates through the media library. Wait for processing to finish, then select the ready templates. Scanned PDFs need a text layer; this feature does not perform OCR. Each template is limited to 20 MiB and 300,000 extracted characters. Select up to 12 templates and 12 script/role pairs, totaling at most 1.5 million characters.
4. Search your saved, approved Style Lab scripts by filename or transcript content. Select each desired script and its role (normally interviewer). Only that role's turns enter the configuration. Scripts appear after approval and local-save acknowledgement in Style Lab.
5. Save the configuration. A Markdown file downloads with the use-case ID and avatar ID in its filename and contents. The same immutable file remains available for download from the saved configuration. Creating a revised interviewer produces a new configuration; existing sessions retain their original one.
6. Choose the saved configuration, enter an interview title, acknowledge sending selected references and conversation content to Gemini, then start. The app navigates to `/interview-studio/{session-id}`, a dedicated conversation page with the avatar on one side and an automatically scrolling transcript on the other. The conversation opens with a saved greeting and first question based on the avatar and genre. The active avatar animates gently while waiting; spoken playback is attempted automatically. When the opening finishes, voice mode requests microphone access and starts listening; allow the browser microphone prompt. The page brings the Your turn controls into view. If speech generation or microphone access fails, text input remains available. Pause voice mode to type instead.

Reference text is used as in-context examples and lexical RAG chunks, with source metadata and role attribution. It does not fine-tune a model. Retrieved references shown beneath a reply indicate which supplied chunks the model cited; they do not prove factual correctness. Reference participants' experiences must not become facts about the new interviewee.

## Gemini settings and activation

Edit the project-root `.env`, keeping the key server-side:

```dotenv
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=your-accessible-text-and-audio-model
GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts
INTERVIEW_DATABASE_URL=
```

The configured `GEMINI_MODEL` handles interview replies and recorded speech transcription. Each new session pins its model name. `GEMINI_TTS_MODEL` independently handles spoken replies; its default is `gemini-2.5-flash-preview-tts`. A configured key does not guarantee model access or quota. See Google's [API key instructions](https://ai.google.dev/gemini-api/docs/api-key) and [speech generation documentation](https://ai.google.dev/gemini-api/docs/speech-generation).

From the project root, install the new database schema and recreate services to load settings:

```sh
docker compose build api web
docker compose run --rm --no-deps migrate
docker compose up -d --no-deps api worker web
```

An ordinary initial `docker compose up -d --build` also runs the migration service. Editing `.env` alone does not update existing containers. Never put the key in a `NEXT_PUBLIC_` variable or source control.

## Conversation, voice and review

Select **Start voice conversation** for hands-free alternating turns: the microphone listens, a pause of about 1.6 seconds after speech sends the answer, the saved reply plays, and listening resumes when playback ends. Use **Pause voice conversation** to stop the loop, or **Send voice answer now** if background noise prevents pause detection. No detected speech for 30 seconds pauses the mode without calling Gemini. Provider/playback failures stop the loop and retain saved text or unsent audio. Browser autoplay restrictions may require pressing Play. Headphones are recommended to reduce echo.

You can also type and send a message, or use manual **Record voice turn**, stop, and send controls. Voice is turn-based rather than an always-open duplex call. Each voice turn allows up to two minutes and 12 MiB; longer interviews consist of multiple turns. Microphone permission and localhost or HTTPS are required. Preview or download an unsent recording before sending; unsent audio exists only in browser memory. Leaving the page can lose unsent material.

With spoken replies enabled, the server generates and saves a WAV recording of the assistant's reply. Text is retained even if speech generation fails; retry voice generation from the reply. Browser autoplay may require pressing Play. The candle reacts to microphone/playback amplitude through Web Audio; motion speed and brightness vary with that signal. Text interaction has a simulated pulse. These are visual effects, not emotion detection. Face avatars are illustrated and lightly animated, not photorealistic talking-head video.

Every sent user input is persisted before provider calls. Original microphone recordings and generated voice replies live in object storage. On failure, the saved turn remains visible and can be retried with the same request ID. A crashed server may leave a generation lease active for up to ten minutes; retries are permitted after it expires. The model sees the latest 40 turns plus selected examples and retrieved reference chunks. Earlier turns remain in the complete saved transcript but are not automatically summarized into the model context.

Select **Save conversation for review**, then **Start to review interview**. This opens `/interview-studio/{session-id}/review`, displaying the entire transcript without the conversation window's scroll limit. Correct the transcript turn by turn, then **Approve conversation script**. Approval freezes the reviewed revision; original text/audio remain alongside corrections. Approved Markdown and JSON snapshots can be downloaded and searched in Studio. Approval does not generate a screenplay yet. Start another session to continue interviewing after review/approval.

Delete an interview to remove its turns, recordings and approval snapshots. Delete its configuration separately after deleting associated sessions. Configurations contain copies of source text: deleting the original Style Lab script or template does not erase those copies. Downloaded local files also remain until removed locally. Biography deletion is blocked while Interview Studio configurations remain.

## Separate local database

By default, `biographer_interviews` uses the same PostgreSQL server and credentials as `DATABASE_URL`, but has its own database and Alembic history (`i0001`). The bootstrap command creates it using the local development PostgreSQL role. A custom `INTERVIEW_DATABASE_URL` must reference an already-created database; run the same migration service against it.

| Table | Purpose |
| --- | --- |
| `interview_configs` | Immutable avatar, genre, source snapshots and configuration Markdown |
| `interview_context_chunks` | Source-attributed retrieval chunks |
| `interview_sessions` | Project/owner, pinned model, status, revision, generation lease |
| `interview_turns` | Ordered original/reviewed text, audio keys, request IDs, cited sources |
| `approved_interviews` | Frozen approved script, full snapshot and SHA-256 |

Primary-library IDs are references across databases, not cross-database foreign keys. API requests verify ownership against the main database. Source search uses the main database's saved Style Lab archive snapshots; approved new interview search uses PostgreSQL full-text search with a GIN index. Reference RAG currently uses bounded lexical scoring, not embeddings.

Open a local SQL shell:

```sh
docker compose exec postgres psql -U biographer -d biographer_interviews
```

```sql
\dt
SELECT id, title, status, revision, created_at
FROM interview_sessions ORDER BY created_at DESC LIMIT 20;

-- Replace the UUID with the chosen biography project.
SELECT id, session_id, revision, script
FROM approved_interviews
WHERE project_id = 'your-project-uuid'
  AND to_tsvector('simple', script) @@ plainto_tsquery('simple', 'childhood garden')
ORDER BY created_at DESC;

SELECT sequence, role, text, original_text, audio_key
FROM interview_turns
WHERE session_id = 'your-session-uuid'
ORDER BY sequence;
```

Direct administrative SQL bypasses application ownership checks. Downstream screenplay generation should use only `approved_interviews` with owner/project scope, retain the snapshot hash and turn citations, and resolve audio keys through authorized object-storage access.

For cloud migration, move PostgreSQL data to managed PostgreSQL (Cloud SQL or RDS) and object storage to GCS/S3 through the existing storage abstraction. S3 is object storage, not a PostgreSQL replacement. Back up both databases and object storage together; restoring SQL alone does not restore recordings. The default local setup uses one PostgreSQL development role for both databases; production deployment should provision explicit database roles, network/TLS controls and backups.


### Pausing, resuming and saving drafts

After **Pause voice conversation**, use **Resume voice conversation** to continue the same interview. If a partial recording remains, Resume sends it first; you can also preview, download or discard it. Sending occurs only when you explicitly resume or send the recording.

**Save conversation for review** retains all sent turns plus any unsent text or recording and makes **Start to review interview** available. Click it to open the separate review page. Pause recording first. This save does not call Gemini, so it also works when provider billing or quota is unavailable. Unsent audio is marked `needs_transcription`: play it and enter/correct the transcript before approval. Saving for review ends the active session; Resume applies to paused active interviews, not finalized review sessions.

## Interview supporting materials

Explicit offers to upload/share pictures, articles or other materials open an
optional dialog. Historical mentions alone should not trigger it. Upload a file,
select it after processing, and attach it; or decline/close (Escape also works)
and continue. Voice pauses during the dialog and resumes if previously active.
**Add interview materials** also opens it manually. New attachments are analyzed in the background before the interviewer offers an interpretation. Existing attachments have an explicit Analyze button.

Approval freezes the transcript and material manifest in local MinIO:
`interviews/<owner>/<session>/scripts/revision-<n>/` contains `script.md`,
`transcript.json`, and `manifest.json`. Attached copies live alongside under
`materials/<material-id>/<filename>`. The approved review page offers
**Save script and materials to local folder**, preserving subfolders in supported
browsers; individual download links are the fallback. Retained recordings are
included. Older approvals retain their existing export behavior.

Migration `i0002` adds `interview_materials` and `interview_upload_requests`
to `biographer_interviews`. Join `session_id` to `interview_sessions.id`;
request `turn_id` identifies the initiating turn. Material records preserve
source asset IDs, storage paths, MIME type, size and SHA-256. Approval snapshots
freeze that provenance. Authenticated session endpoints expose `/materials`
(GET/POST), `/upload-requests/{id}/decline` (POST) and `/bundle` (GET).

Deleting an original library asset preserves the interview copy. Deleting the
interview removes its copies and approved archive while retaining library originals.
PostgreSQL holds metadata and relationships; object keys can migrate to cloud storage.

## Analysis, confirmation, and continued conversation

Attaching new materials queues a durable Temporal job. The page shows progress by
completed sections and persists progress across reloads. The interviewer presents
one completed interpretation at a time, asks whether it is accurate, and invites
the interviewee's own description. Their replies, corrections and memories inform
subsequent questions. The model classifies explicit confirmation/correction/refusal;
the exact user turn and original words are retained alongside that classification.
AI observations remain provisional and separate from the interviewee's account.

Supported uploads now include:
- Images: JPEG, PNG, WebP, HEIC/HEIF, GIF, TIFF, BMP, AVIF.
- Documents: PDF (including scans), DOC/DOCX, ODT, RTF, TXT, Markdown, HTML, CSV.
- Presentations/spreadsheets: PPT/PPTX, ODP, XLS/XLSX, ODS.
- Audio: MP3, WAV, M4A, AAC, FLAC, OGG/Opus, AIFF.
- Video: MP4/M4V, MOV, MPEG, WebM, AVI, MKV, 3GP, WMV.

Office files are converted by LibreOffice with macros disabled; PDF pages retain
visual content. Images are normalized to JPEG up to 2048px; every GIF/TIFF frame
or page is processed. Recordings are split into two-minute sections, with video
sampled at 2fps and audio retained. Text uses 20,000-character sections. Section
results are synthesized in bounded groups and retained as provenance. This is
content understanding, not a guaranteed verbatim transcript or frame-perfect
inspection. Corrupt, encrypted, unsupported-codec or oversized normalized sections
produce an explicit error; users can retry or skip and describe the material.
Existing upload and four-hour recording-duration constraints still apply.

The provider receives actual material content using Gemini multimodal input
([Google documentation](https://ai.google.dev/gemini-api/docs/generate-content/document-processing)).
No live provider call is necessary for fixture validation. Every section incurs
a provider call; long recordings, PDFs, or animations may require many calls.

Migration `i0003` adds analysis state, generation, progress, output, errors,
discussion turn ID and confirmation JSON to `interview_materials`. Existing files
are not automatically submitted. New session routes:
`/materials/{id}/analyze` (retry/start), `/materials/{id}/skip`, and
`/materials/discuss` (idempotently appends the next confirmation question).
Skipping prevents an in-flight result from being published; an already-running
provider request may still complete. Approval waits for active analysis to finish
or be skipped; approved snapshots include analysis and interviewee provenance.

## Trace a file from an interview UID

The interview UID is `interview_sessions.id` (also called `session_id` in APIs).
Every attached copy has an indexed foreign key `interview_materials.session_id`.
Files live at `interviews/<owner UID>/<interview UID>/materials/<material UID>/<filename>`.
The material UID distinguishes identical filenames, and SHA-256 verifies contents.

New approved Markdown exports include the interview UID, each material UID,
original asset UID, storage key, checksum, and a relative link to the archived file.
Keep the downloaded archive folder structure intact for links to work. JSON
snapshots and manifests also include each material's session ID. Existing approved
exports remain immutable; their files are still traceable through the database
and the authenticated `GET /api/interviews/sessions/<UID>/materials` endpoint,
which returns fresh download links.

In the separate `biographer_interviews` database, set the UID in psql and query:

```sql
\set interview_uid 'PASTE-INTERVIEW-UID-HERE'
SELECT m.session_id AS interview_uid, m.id AS material_uid,
       m.asset_id AS original_asset_uid, m.filename, m.mime_type,
       m.storage_key, m.sha256, m.request_id, r.turn_id AS upload_offer_turn
FROM interview_materials AS m
LEFT JOIN interview_upload_requests AS r ON r.id = m.request_id
WHERE m.session_id = :'interview_uid'
ORDER BY m.created_at, m.id;
```
