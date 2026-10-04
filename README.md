# LifeStoryBiographer_Codex

AI Biographer helps collect the memories and source material for a biographical film. This repository implements accounts, biography projects, a media library, durable media processing, a reviewed interviewer Style Lab, and Interview Studio with configurable avatars, reference retrieval, voice/text conversations, and script approval. Screenplay Editor and Cinema Studio remain future phases.

## Start the application

Requires Docker Desktop with its engine running. On Apple silicon, Docker can run this stack with Rosetta disabled.

```sh
cd /Users/antongchen/Projects/LifeStoryBiographer_Codex
python3 scripts/setup.py
docker compose up -d --build
```

Open **http://localhost:3000**, create an account, and choose **New biography**. Inside the biography, confirm permission to use your files and drag them into the Media Library. The first build downloads dependencies and compiles MinIO from its pinned upstream source; subsequent starts reuse the images.

- API and interactive contracts: http://localhost:8000/docs
- Temporal workflow history: http://localhost:8233
- Local storage console: http://localhost:9001 (development credentials are in `.env`)

`python3 scripts/setup.py` creates `.env` with a random authentication secret and preserves existing settings. `.env` is excluded from Git. `docker compose stop` stops the stack while retaining project data in named volumes. `docker compose down` removes containers without deleting those volumes.

## What works

- Auth.js sign-in and registration, encrypted session cookies, hashed API sessions, and logout revocation.
- Biography project creation, reading, editing, and deletion; OWNER, SUBJECT, EDITOR, and VIEWER authorization; audit records.
- Signed multipart uploads with progress, pause/reselection recovery, idempotent completion, ownership declaration, and actual content validation.
- JPG/JPEG, PNG, WebP, HEIC; MP4, MOV, MPEG/MPG, M4V, WebM; MP3, WAV, M4A, AAC; UTF-8 TXT/MD, DOCX, and PDF.
- Permanent originals, SHA-256 checksums, metadata, image/video thumbnails, video/audio proxies, preview, notes, downloads, deletion, and failed-processing retries.
- Style Lab profiles, source recording review, timestamped transcript correction, evidence-backed patterns and examples, explicit approval, and immutable private style versions.
- Optional server-side Gemini transcription and style analysis through checkpointed Temporal jobs, adapted from VocalExtract-Pro’s sequential audio segmentation.
- PostgreSQL/pgvector migrations, Redis authentication throttling, a database dispatch record, and Temporal workflows with bounded retries.

Audio/video recordings have no application-level file-size cap; uploads use adaptive multipart chunks within storage-service limits and available disk space. Images/documents retain their existing 2 GiB upload limit; audio/video duration is limited to four hours and text documents to 20 MiB. Processing may reject damaged, encrypted, or unusually compressed documents. Style Lab can transcribe recordings with server-configured Gemini access, or accept a manually entered transcript.

## Interview Studio

Open **Interview Studio** from the sidebar. Choose an avatar and genre, optionally select uploaded templates and saved Style Lab scripts, then save the interviewer configuration. Start a voice or text interview, finish for review, and approve the corrected script. New interviews are stored in the separate `biographer_interviews` PostgreSQL database. See [the Interview Studio guide](docs/interview-studio.md) for setup, voice behavior, storage, queries and limitations.

## Verify

```sh
# Domain and API integration tests (includes isolation, idempotency, and invalid files)
docker compose run --rm --no-deps api python -m pytest -q

# Real JPG, MP4, MP3, DOCX and multipart TXT uploads -> Temporal -> verified download
docker compose run --rm --no-deps -e RUN_LIVE=1 -e STORAGE_CONNECT_HOST=minio api \
  python -m pytest tests/integration/test_stack.py -q

# Python formatting and lint
docker compose run --rm --no-deps api ruff check --no-cache .

# TypeScript and browser acceptance (uses installed Google Chrome)
cd apps/web
npm ci
npm run typecheck
npm run test:e2e
```

Browser tests create synthetic accounts and files, check desktop and mobile layouts, then remove their projects and media. They do not use your personal materials. Screenshots are written to `/private/tmp/lifestory-previews` on this Mac.

## Optional malware scanning

Set `SCANNER=clamav` in `.env`, then run `docker compose --profile scan up -d --build`. Allow ClamAV to download its signatures before uploading files. Processing fails closed if a configured scanner is unavailable or rejects a file. Scanning is explicitly disabled for the default development stack. Production configuration requires it and encrypted HTTPS storage.

## Validation

Interview Studio adds backend and Chrome acceptance coverage for configuration, voice/text interaction, approval and separate PostgreSQL retrieval. See [validation details](docs/validation.md) for the exercised behavior and remaining limits.

## Repository

- `apps/web`: Next.js, strict TypeScript, Auth.js, Tailwind, shadcn-style components, TanStack Query.
- `apps/api`: FastAPI, Pydantic, SQLAlchemy, Alembic, provider contracts, and Temporal worker.
- `infrastructure/minio`: reproducible development object-storage build.
- `tests/evals`: source-grounding and sensitive-interview evaluation fixtures for later AI phases.
- `docs/product-specification.md`: your original architecture and phased implementation specification.
- `docs/architecture.md`: authorization, upload recovery, processing, and current production limits.

See [Style Lab setup and workflow](docs/style-lab.md) for recording review, Gemini configuration, evidence-backed patterns, and private version publication. Reference-question integration is pending the user’s list; practice interviews and coverage reporting follow that reviewed plan.

### Script review and memory

Style Lab recording cards open a separate script-review page. Approve and save TXT/JSON to a folder selected in desktop Chrome or Edge; after the write succeeds, the script becomes searchable in local PostgreSQL. See [conversation memory architecture](docs/conversation-memory.md) for versioning, recovery, data boundaries, and the AWS/GCP migration design.

### Duplicate-upload reminders

Before uploading materials (including Style Lab recordings), the app checks this user's earlier uploads across biographies they can still access. A matching filename (case-insensitive) and byte size triggers a reminder showing the existing biography and file. Cancel skips that file; OK explicitly uploads another copy. Multipart resumption of the same upload is excluded. The API also requires an explicit duplicate override when a match exists. This is a metadata reminder, not content-hash deduplication: renamed files may not be detected, and different contents with the same name and size can trigger a reminder. Existing audit records identify uploaders, so no backfill or database migration is required.

### Speaker role defaults and local corrections

The script-review page has one **Assign speaker roles** panel above review/approval. It lists A, B, C and other speaker labels across the entire recording, including pages not currently displayed. Selecting a role saves immediately and applies it to matching base labels across sections (`1: Speaker A`, `2: A`, etc.). The panel reports unassigned sentence counts, local overrides, and missing interviewer/participant roles so approval requirements are visible before saving.

Every sentence displays its role and an adjacent dropdown. Changing that dropdown saves an individual override immediately; subsequent top-panel changes preserve it. The expanded **Edit words & role** form remains available for words, timing, labels and returning a turn to a shared role. Text-only edits do not propagate roles. Approved archive versions remain unchanged.

Section-generated speaker labels are not a verified identity match. The top panel explicitly groups their base labels as requested; listen for label reuse by a different person and correct those sentences locally. Defaults never propagate into another recording. No new database migration is needed beyond the existing `0005` local-override column.

### Delete processing and scripts

Stopped, interrupted, and completed transcription cards provide **Delete processing & script**. The script-review page also provides **Delete script**, including for manually entered transcripts. Both require confirmation and are disabled while this profile has active processing; stop it and wait for the worker to acknowledge cancellation first.

Deletion removes the working transcript, approved archive versions, searchable memory, dependent draft patterns and published style versions, the source's transcription jobs, and profile analysis history/checkpoints that may retain derived content. Other recordings and their transcripts remain. The original uploaded recording stays available for fresh transcription. Previously exported local TXT/JSON files remain on your computer and must be deleted there separately. An analysis card's **Delete processing record** removes only that job/checkpoint, retaining existing scripts and patterns. No schema migration is required.
