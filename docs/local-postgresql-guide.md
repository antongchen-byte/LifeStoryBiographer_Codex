# Local PostgreSQL setup and query guide

The PostgreSQL database for LifeStoryBiographer_Codex runs inside Docker Desktop. The following runtime details were verified on September 28, 2026; versions may change after upgrades.

| Setting | Verified value |
|---|---|
| PostgreSQL version | 16.15 |
| Database name | `biographer` |
| Database user | `biographer` |
| Docker Compose service | `postgres` |
| Persistent storage | Compose volume `postgres_data` |
| Schema migration | `0005` |
| Vector-search extension | pgvector 0.8.6 installed |

The database survives ordinary container restarts. Its files live in Docker's managed storage, not in your selected script-export folder. Removing the database volume removes that stored data. PostgreSQL is accessible within Docker's network; port 5432 is not currently published to the Mac.

The API and background worker connect through SQLAlchemy. Configuration is in [docker-compose.yml](../docker-compose.yml), with application connection settings supplied through the project-root `.env`. Database models are in [models.py](../apps/api/app/models.py), and schema changes are managed through [Alembic migrations](../apps/api/alembic/versions/).

## What is stored where

| Location/table | Contents |
|---|---|
| MinIO storage | Uploaded recordings and other original files |
| `projects`, `interviewer_profiles` | Biography workspaces and Style Lab profiles |
| `media_assets`, `style_sources` | Recording metadata and links to profiles |
| `transcript_turns` | Editable transcript text, speakers, roles, and timestamps |
| `transcript_archives` | Approved, immutable script snapshots and local-save status |
| `conversation_memory_turns` | Searchable transcript passages, created after local saving succeeds |
| Your selected folder | Exported TXT and JSON copies |

Keyword search is implemented. Although pgvector is installed, semantic embeddings are not yet populated. Exported scripts are separate from the database; saving a TXT/JSON copy does not back up accounts, projects, or processing state.

## Open the database

Run these commands in Terminal while Docker Desktop and the project database are running:

```bash
cd /Users/antongchen/Projects/LifeStoryBiographer_Codex

docker compose exec postgres psql -U biographer -d biographer
```

You will see a `biographer=#` prompt. Run the following inside `psql` to make this session read-only and inspect the tables:

```sql
SET default_transaction_read_only = on;

\dt
\d transcript_turns
\d transcript_archives
```

- `\dt` lists tables.
- `\d table_name` describes a table.
- `\q` exits.

The read-only setting applies to this connection, not to the running app. SQL statements end with a semicolon; the `psql` commands beginning with a backslash do not need one. If output opens in a pager, press `q` to return to the prompt, or run `\pset pager off` to disable paging.

## Find your Style Lab profiles

Replace the email below with your app login email:

```sql
\set email 'your-email@example.com'

SELECT
    p.id AS profile_id,
    p.name AS profile_name,
    pr.title AS biography
FROM interviewer_profiles p
JOIN users u ON u.id = p.owner_id
JOIN projects pr ON pr.id = p.project_id
WHERE u.email = :'email'
ORDER BY p.name;
```

Copy a returned profile ID into this variable. Keep the same `psql` session open for subsequent queries:

```sql
\set profile_id 'paste-profile-id-here'
```

The `:'variable_name'` syntax safely quotes a variable as a SQL string in `psql`. It is not syntax to paste unchanged into a different SQL client.

## Read working transcripts

```sql
SELECT
    a.original_filename,
    t.speaker,
    t.role,
    t.role_override,
    t.start_ms / 1000.0 AS start_seconds,
    t.text
FROM transcript_turns t
JOIN style_sources s ON s.id = t.source_id
JOIN media_assets a ON a.id = s.asset_id
WHERE s.profile_id = :'profile_id'
ORDER BY s.id, t.start_ms, t.id
LIMIT 100;
```

`role_override = true` identifies a sentence-level role correction. These are the editable working transcripts, not frozen approved versions.

## Check approved scripts and local-save status

```sql
SELECT
    id AS archive_id,
    snapshot->>'filename' AS filename,
    revision,
    created_at AS approved_at,
    saved_at,
    folder_label
FROM transcript_archives
WHERE profile_id = :'profile_id'
ORDER BY created_at DESC;
```

A blank `saved_at` means local saving has not been confirmed, so that version is not indexed in conversation memory. `folder_label` is the selected folder's display name, not a server-accessible filesystem path. The save acknowledgement does not track later changes to or deletion of files on your Mac.

## Search saved conversation memory

This query searches the latest saved revision of each recording:

```sql
\set search_words 'school childhood'

WITH latest AS (
    SELECT source_id, MAX(revision) AS revision
    FROM transcript_archives
    WHERE profile_id = :'profile_id'
      AND saved_at IS NOT NULL
    GROUP BY source_id
)
SELECT
    a.snapshot->>'filename' AS filename,
    a.revision,
    m.speaker,
    m.role,
    m.start_ms / 1000.0 AS start_seconds,
    m.text
FROM conversation_memory_turns m
JOIN transcript_archives a ON a.id = m.archive_id
JOIN latest l
  ON l.source_id = a.source_id
 AND l.revision = a.revision
WHERE a.profile_id = :'profile_id'
  AND to_tsvector('simple', m.text)
      @@ plainto_tsquery('simple', :'search_words')
ORDER BY a.source_id, m.start_ms
LIMIT 50;
```

This searches for the supplied words together within a passage. It is keyword search, not natural-language question answering. The `simple` configuration does not perform English stemming; languages needing word segmentation require further search support. If no results appear, try one word and verify that a script has a non-null `saved_at`.

Direct SQL does not automatically apply the app's account-access checks. The email/profile filters above keep queries focused on your own material. The database can also contain synthetic test accounts and their data.

For archive lifecycle and future cloud migration details, see [Conversation memory architecture](conversation-memory.md).
