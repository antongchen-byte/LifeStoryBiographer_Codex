# Production Editor (local)

Regular accounts keep their existing modules, account permissions, media workflows, interviews, screenplay editing and video generation. Production Editor is an additional capability; public registration cannot grant it. It does not grant billing, security settings or account administration.

After signing in as an editor, **Production projects** allows searching owners and biographies. **Open project** activates a tab-local, server-validated project context. A persistent banner identifies the owner and project. The editor remains the authenticated actor; new configurations, interviews, screenplays and Cinema productions retain the owner's ID. Navigation carries the selected screenplay into Cinema Studio. Exit the production workspace to return to personal work.

Opening an existing production creates or resumes an editor draft. A new draft copies the latest original screenplay, sections, material selections, exclusions and completed video attempts without changing the original. Unpublished editor screenplay/clip drafts are inaccessible to ordinary accounts. Earlier takes remain available. Production history captures metadata, transcripts and screenplay snapshots before changes, with the editor ID. Download a snapshot or restore its screenplay as a new draft. Original media objects are not copied into JSON snapshots; they remain in object storage. Editors cannot delete source originals, projects or memberships in production mode.

After reviewing a completed stitched film, **Publish to owner** makes that exact output available under **Published videos** in the owner's biography. Publication validates that every current clip is approved and the stitched output matches that sequence. It does not expose editor drafts or alternate takes. Normal owner generation/review/download workflows remain available as before.

## Provisioning

An operator on the local machine can run:

```sh
docker compose exec api python -m app.manage_production_editor antongchen@gmail.com --create
```

The command prompts for a password only when creating a new account. It grants the production capability to an existing account without changing its password. Use `--revoke` to remove the capability. Passwords are hashed and never written into source files. The requested account is pending a password of at least 10 characters.

Migration `0007` adds the capability (false for every existing account), production history and publication records. No user is automatically promoted. The role and workspace are checked in the backend on every request; a forged browser header does not grant access. Job requests retain actor and project IDs while immutable production snapshots and storage paths retain the owner.

Validation includes the existing API suite plus editor permission/isolation, version-copy, restoration and publication checks. Browser checks use mocked providers and accounts. Live paid generation and user media were not used in validation. GCP is unchanged.

## Sharing read-only module versions

At the bottom of each selected project's module page, **Save editor version for owner** previews the page's text and current form values. **Confirm and share version** stores a new immutable copy with its module, project, owner, editor and timestamp. This action does not update the project's working records, submit other forms, upload files or start generation. It includes typed field changes without requiring the module's usual save action first. Existing module save actions retain their existing behavior.

Owners open **Editor versions** in My Biographies to read or download the Markdown copy. Each save creates a separate version; retrying the same request does not duplicate it. Versions contain text and field selections, not playable video or copies of media files. Media stays in its existing library, and finished videos still use **Publish to owner**. Migration `0008` adds the immutable review table. Only the selected project's Production Editor can share a copy; only its owner or an authorized editor in that project can read it.

## Isolated editable projects from shared versions

New shared versions also pin the project's saved database records and separate media objects. Finish active jobs and save interviews for review before sharing. The selected screenplay is pinned when one is selected; page text can include unsaved field values, but the editable copy uses saved records only. Owners choose **Open as a separate editable project** from the version page. This creates new project, configuration, interview, screenplay and clip IDs, copies media into independent storage, preserves the owner and read-only source, and opens an isolated workspace. Reopening the same version resumes its existing editable copy.

The workspace header remains visible across all five modules. Server-validated `X-Workspace-Project` scope limits project/resource reads, writes and selectors; leaving the workspace reloads the personal dashboard. Cinema's selector shows each full screenplay UID. Old text-only versions cannot reconstruct historical project records: an editor must share a new complete version. Migration `0009` stores complete snapshots without falsely backfilling old versions from current data.
