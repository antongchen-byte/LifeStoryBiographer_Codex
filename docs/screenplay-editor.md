# Screenplay Editor

Open **Proceed to Screenplay Editor** after saving an interview for review, or open Screenplay Editor from navigation. Select a database interview, reopen a saved screenplay, or import a UTF-8 `.md` file into a biography workspace.

Review/edit the conversation and material descriptions before generation. These edits belong to the screenplay; original interviews and approved exports remain unchanged. Imported filenames do not give the browser access to local photos: attach the actual files through the materials panel. Imported interview UID metadata is provenance, not authorization to read a database interview. Imports without a UID receive a new UID.

Choose 1–30 approximately 60-second sections (default 3), consent to Gemini processing, then **Convert conversation to screenplay draft**. Review the formatted preview and edit scene headings, action, character cues, parentheticals, dialogue and transitions. Save section edits, then choose **Break into video subsections**: six 10-second or four 15-second units per section. Every subsection has its own editable content, notes, material references, UID and save button. Save buttons persist all current editor changes together.

**Save final screenplay and download Markdown** saves a revisioned `.md` object and downloads it. The database already contains every saved section/subsection. The Markdown uses monospaced blocks with element indentation; the preview uses CSS alignment. Section timing is estimated, not a guarantee of printed pagination, performance duration or generated-video duration. Subsections total exactly 60 seconds per section.

Formatting follows the requested specification and [Final Draft element guidance](https://www.finaldraft.com/learn/screenplay-formatting-elements/). Proposed staging and reconstructed dialogue belong in production notes. Gemini receives reviewed text, material descriptions and confirmations; filenames alone are not treated as image analysis.

## Storage and querying

Migration `i0004` creates three tables in `biographer_interviews`:

- `screenplays`: owner/project, interview UID, optional interview FK, original/reviewed Markdown, material references, model, revision, generation state and exports.
- `screenplay_sections`: section UID, screenplay FK, position and structured content; each targets 60 seconds.
- `screenplay_subsections`: subsection UID, section FK, position, seconds and structured content.

Database-sourced screenplays protect their interview and materials from deletion while referenced. Additional imported materials are copied into the screenplay archive. Deleting a screenplay removes its own copies and exports, preserving interview and library originals.

Export path: `interviews/<owner>/<interview UID>/screenplays/<screenplay UID>/revision-<n>/screenplay.md`.

Every exported subsection names its section UID and interview UID. Materials include UIDs, storage keys and SHA-256 checksums. Query by interview UID:

```sql
SELECT s.interview_uid, s.id AS screenplay_uid,
       p.id AS section_uid, p.position AS section_number,
       u.id AS subsection_uid, u.position AS subsection_number,
       u.seconds, u.content
FROM screenplays s
JOIN screenplay_sections p ON p.screenplay_id = s.id
JOIN screenplay_subsections u ON u.section_id = p.id
WHERE s.interview_uid = 'PASTE-INTERVIEW-UID'
ORDER BY s.created_at, p.position, u.position;
```

## Generation and validation

Database-backed Temporal jobs provide polling, progress, stopping and explicit regeneration after failure. Previous drafts are preserved until validated replacements are ready. Stopping fences late results; an in-flight provider request may finish. No automatic paid retry occurs.

Source/material-context edits mark the draft stale; section edits mark its subsections stale. Regenerate downstream content before export. Revision checks protect concurrent edits. Foreign IDs, unavailable material references, invalid dialogue cues and incorrect duration totals are rejected.

Authenticated routes are under `/api/interviews/screenplays`: collection GET/POST; `/{id}` GET/PUT/DELETE; `/{id}/generate`, `/{id}/stop`, `/{id}/export` POST; material attach/download endpoints. Sources are limited to 200,000 characters; import excerpts for larger conversations. Lists show up to 100 saved screenplays/interviews.

API tests cover both source types, ownership, both durations, editing, stale content, generation failures/stopping and exports. Live PostgreSQL and browser tests use deterministic provider fixtures. Live Gemini quality and real video timing require separate validation.
