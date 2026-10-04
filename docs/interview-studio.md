# Interview Studio

Interview Studio creates an AI interviewer and records new interviews separately from the Style Lab reference library. Open `/interview-studio` from the sidebar after signing in. You must own the selected biography workspace.

## Configure and start

1. Select the biography, then **Ember** (candle), **Maya** (female illustration), or **Eli** (male illustration). Keep the suggested name or enter your own.
Ember defaults to calm and reflective, Maya to warm and curious, and Eli to thoughtful and focused. These are individual character choices, not gender-based traits. The selected personality is saved in the configuration Markdown and used alongside genre and references in conversation prompts. Renaming an avatar retains its personality. Existing saved configurations keep their previous behavior; save a new configuration to adopt the new defaults.

2. Select a genre: life story, oral history, reflective, documentary, or career. This provides the default approach even without reference files.
3. Optionally upload multiple TXT, Markdown, PDF, or DOCX templates through the media library. Wait for processing to finish, then select the ready templates. Scanned PDFs need a text layer; this feature does not perform OCR. Each template is limited to 20 MiB and 300,000 extracted characters. Select up to 12 templates and 12 script/role pairs, totaling at most 1.5 million characters.
4. Search your saved, approved Style Lab scripts by filename or transcript content. Select each desired script and its role (normally interviewer). Only that role's turns enter the configuration. Scripts appear after approval and local-save acknowledgement in Style Lab.
5. Save the configuration. A Markdown file downloads with the use-case ID and avatar ID in its filename and contents. The same immutable file remains available for download from the saved configuration. Creating a revised interviewer produces a new configuration; existing sessions retain their original one.
6. Choose the saved configuration, enter an interview title, acknowledge sending selected references and conversation content to Gemini, then start.

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

Type and send a message, or press **Record voice**, speak, stop, and send the recording. Voice is turn-based rather than an always-open duplex call. Each voice turn allows up to two minutes and 12 MiB; longer interviews consist of multiple turns. Microphone permission and localhost or HTTPS are required. Preview or download an unsent recording before sending; unsent audio exists only in browser memory. Leaving the page can lose unsent material.

With spoken replies enabled, the server generates and saves a WAV recording of the assistant's reply. Text is retained even if speech generation fails; retry voice generation from the reply. Browser autoplay may require pressing Play. The candle reacts to microphone/playback amplitude through Web Audio; motion speed and brightness vary with that signal. Text interaction has a simulated pulse. These are visual effects, not emotion detection. Face avatars are illustrated and lightly animated, not photorealistic talking-head video.

Every sent user input is persisted before provider calls. Original microphone recordings and generated voice replies live in object storage. On failure, the saved turn remains visible and can be retried with the same request ID. A crashed server may leave a generation lease active for up to ten minutes; retries are permitted after it expires. The model sees the latest 40 turns plus selected examples and retrieved reference chunks. Earlier turns remain in the complete saved transcript but are not automatically summarized into the model context.

Select **Finish & review conversation**, correct the transcript turn by turn, then **Approve conversation script**. Approval freezes the reviewed revision; original text/audio remain alongside corrections. Approved Markdown and JSON snapshots can be downloaded and searched in Studio. Approval does not generate a screenplay yet. Start another session to continue interviewing after review/approval.

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
