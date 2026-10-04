# Script archive and conversation memory

## Implemented workflow

Use **Open transcript** (or **Transcript workspace** for an empty recording) on a Style Lab recording to open its dedicated review page. Listen, correct words/timestamps, and identify every speaker. **Approve & save to local folder** opens the browser's folder picker, freezes the reviewed revision, and writes two UTF-8 files: a readable `.txt` and a lossless, schema-versioned `.json`.

Desktop Chrome and Edge support this folder flow on localhost/HTTPS. Other browsers show an explanation instead of pretending a download was saved. The picker is invoked within the button's user gesture. The app requests only the selected folder; it retains its display name, not a full filesystem path or persistent permission handle. Folder selection is required again for another save.

The JSON SHA-256 is verified before writing. Both files are closed and read back before the browser acknowledges the save. Only then does the API transaction create searchable memory rows. Cancelling the picker does not approve or index anything. A failed file write or acknowledgement leaves the approved version available under **Retry local save**; it may leave a partial local file. Retry uses the same immutable version and filenames, and indexing is idempotent. A re-save of an already indexed archive does not change its original save acknowledgement. The server trusts the authenticated browser's acknowledgement; it cannot independently inspect a user's disk or monitor later deletion of local files.

Working drafts already live in local PostgreSQL so long processing jobs and edits survive reload. The new *searchable memory* is built after saving the approved script. Approval snapshots are stored before disk export so a failed save can be retried exactly. These are distinct stages, shown in the UI.

Approved versions remain unchanged when draft words or roles are edited. Revision checks reject approval of a stale page. Use **Delete script** to remove the working transcript, approved archives, searchable memory, dependent patterns and published versions, and related processing checkpoints while retaining the recording. Source recording deletion is blocked while approved archives reference it, just as published style evidence is protected; deleting the script first clears these references. Deleting the entire profile deletes its database archives and memory index through foreign-key cascades; exported files on the user's disk remain untouched.

## Local database design

Keep the existing PostgreSQL database rather than introducing a second SQLite store. Docker's persistent `postgres_data` volume holds local data. Back up this volume through PostgreSQL tools; local TXT/JSON copies preserve scripts but are not a backup of accounts, profiles, or processing state.

| Table | Purpose |
| --- | --- |
| `style_sources`, `transcript_turns` | Mutable working transcript, recording identity, roles and time ranges |
| `transcript_archives` | Immutable snapshot per source revision; approving owner and UTC approval time in JSON; schema version, SHA-256, local-save acknowledgement and folder display name |
| `conversation_memory_turns` | Searchable copies inserted after confirmed save, with archive ID, original turn ID, speaker, role, text and millisecond time range |

Every archive is scoped to an owner-authorized profile/project. Search checks that scope before querying and returns citations to the exact approved version. It searches the latest **saved** revision of each recording, so old corrections do not appear as duplicate current memories; old archives can still be opened and exported. Editing a draft does not remove the last approved version from search.

PostgreSQL uses a GIN index on `to_tsvector('simple', text)` with parameterized `plainto_tsquery`. This provides token matching without English stemming; it is not semantic/fuzzy search, and languages needing segmentation (such as Chinese) need a tokenizer strategy before claiming full language support. SQLite unit fixtures use literal substring search; the real-stack browser test exercises PostgreSQL token search. Queries are paginated and capped. No Gemini call is made for indexing or searching.

Endpoints (authenticated, owner-only):

- `POST /api/profiles/{profile}/sources/{source}/archives` with the displayed `revision`: validate completed transcription and roles, approve and export an immutable snapshot.
- `GET .../sources/{source}/archives`: version/save state listing.
- `GET /api/profiles/{profile}/archives/{archive}`: exact approved JSON and TXT.
- `POST .../archives/{archive}/saved` with `sha256`, `folder_label`: idempotent acknowledgement and atomic indexing.
- `GET /api/profiles/{profile}/memory?q=...&offset=0&limit=30`: latest saved script search with speaker/time/version citations.

## Future interview memory

Current records are explicitly `scope: reference_interview`. They support retrieval from Style Lab source recordings; they must not silently become facts about a new interviewee. The following is a design for the next phase, not implemented tables:

1. `interview_sessions`: project, subject/person ID, owner, configuration version, started/ended times, consent status.
2. `session_turns`: session ID, monotonic sequence, speaker/person ID, role, timestamp, immutable original content; corrections as new revisions. Unique `(session_id, sequence)` supports replay and idempotency.
3. `memory_items`: subject/person ID, memory kind (event, relationship, preference, unresolved question), statement, confidence, review state, valid-time interval, created time and superseded-item ID. Keep extraction output separate from verified statements.
4. `memory_evidence`: memory item → exact session/archive version and turn/time span. Every answer should cite source evidence; conflicting claims remain distinct until reviewed.
5. `memory_embeddings`: memory/turn ID, model and embedding version, dimensions, vector and content hash. Use pgvector later for semantic retrieval alongside full-text search; generate embeddings only after approval and configured processing consent.
6. Reference-question coverage belongs to a session/configuration version. Track asking, answering and deferral separately. The requested question list is still pending.

Retrieval must first filter by owner, project, subject and scope, then combine lexical/semantic candidates, rerank, and return cited passages. Do not feed source text as instructions. Do not mix interviewer-style behavior with source participant facts or a new subject's personal memory.

## Cloud transition

S3 and Google Cloud Storage store **objects**, not a running queryable PostgreSQL database. Use two separate migration tracks:

| Local | AWS | GCP |
| --- | --- | --- |
| PostgreSQL | RDS for PostgreSQL (or Aurora PostgreSQL after compatibility checks) | Cloud SQL for PostgreSQL |
| Original media in local MinIO; approved TXT/JSON in a chosen folder | Private S3 bucket | Private Google Cloud Storage bucket |

For a later cloud export, add an archive-object location table keyed by immutable archive ID, format, content SHA-256, backend (`local`, `s3`, `gcs`), bucket and relative object key. Keep storage location outside the signed/canonical snapshot so relocating files does not change evidence hashes. Never persist expiring signed URLs as identifiers. The current browser directory label is informational and cannot be used by a server as an accessible path.

Migration sequence: freeze writes or use a managed replication migration; dump/restore PostgreSQL including schema/migrations and validate row counts; explicitly select/upload the local archives and copy MinIO media; verify hashes; record cloud object locations; switch database/storage configuration; test owner isolation, archive retrieval, signed links, search and restore before cutover. Keep rollback backups. Existing S3 media adapter supports an S3 endpoint; GCS needs an adapter and cloud archive import/export is not yet implemented. No cloud credentials or resources are created by this feature.

References:
- [PostgreSQL text-search indexes](https://www.postgresql.org/docs/current/textsearch-indexes.html)
- [Browser file system access and user gestures](https://developer.chrome.com/docs/capabilities/web-apis/file-system-access)
- [Cloud SQL PostgreSQL overview](https://docs.cloud.google.com/sql/docs/postgres/introduction)
- [Amazon RDS for PostgreSQL](https://aws.amazon.com/rds/postgresql/)
- [AWS database and S3 file storage integration](https://aws.amazon.com/blogs/database/work-with-files-in-amazon-aurora-postgresql/)
