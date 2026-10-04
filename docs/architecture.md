# Foundation architecture

The foundation implements Phase 1 and the first task in [the product specification](product-specification.md).

## Request and storage flow

The browser signs in with Auth.js Credentials. The API stores scrypt password hashes and opaque sessions as SHA-256 token hashes. Auth.js holds the API token inside its encrypted, HTTP-only JWT cookie. The public session response contains the user's identity, never the API token. Next.js forwards authorized JSON requests through a same-origin proxy; its streamed request-body limit is 256 KiB. Large media travels directly to S3-compatible storage through signed multipart URLs.

Every project request checks membership. OWNER can manage collaborators and delete an empty project. OWNER, SUBJECT, and EDITOR can edit projects and media. VIEWER can read validated media. Unrelated users receive 404. Download URLs expire after five minutes; part URLs expire after fifteen minutes. A renewed upload session lists existing parts. Upload ownership is declared before a session is created.

## Durable processing

Upload completion locks the asset row, verifies the storage parts and their sizes, completes the object, then commits the asset status and a processing-job record in one transaction. If object completion succeeds but the database commit fails, a repeated completion recovers from the object metadata. Repeated completion never creates a second job.

The dispatcher reads pending jobs and starts `ProcessMediaWorkflow` with an ID derived from the database job ID. A crash between dispatch and recording dispatch is safe: the same workflow ID is recognized as already started. Temporal stores its development history on a named volume. Worker restarts resume processing. Activities retry infrastructure failures three times; invalid media is non-retryable. A final activity records terminal failures so the UI can offer retry.

Processing downloads the original, optionally runs ClamAV, validates its content with libmagic and parsers, calculates SHA-256, extracts metadata, and creates derived previews. Derived object keys are deterministic so retries overwrite the same artifacts. FFmpeg runs as an argument array with time limits. Filenames never become commands. Media cannot be downloaded until validation succeeds. Deletion is blocked while queued or processing, and deletes the original and known derived paths.

## Dependencies and boundaries

- `ObjectStorage` is the permanent storage interface; `S3Storage` is its MinIO/S3 implementation. A native GCS implementation can be added behind this interface.
- `MalwareScanner` has a ClamAV implementation. Development explicitly disables scanning unless the `scan` profile and `SCANNER=clamav` are enabled. Production settings refuse disabled scanning, unencrypted objects, HTTP storage endpoints, and development storage credentials.
- AI contracts cover structured text, multimodal analysis, ephemeral Live sessions, and asynchronous video generation. No Google calls or synthetic AI output are implemented in this phase.
- Request IDs and audit events contain identifiers and action names. SQL parameter logging is disabled. Raw interview text and passwords are not included in ordinary access logs.

## Deliberate limits

Local authentication has registration, login, expiration, revocation, and throttling. Email verification, recovery, MFA, invitations by email, and full account deletion are future production work. The collaborator API grants access only to accounts that already exist.

The Compose stack is a development deployment bound to loopback. It uses a Temporal development server, not Temporal Cloud. It is not a production infrastructure definition. ClamAV is an optional resource-intensive profile; its live signature update and scan service require separate operational verification. Transcoding has bounded duration; it is not yet an elastic media cluster. The current UI lists up to 50 projects and 100 assets per project, while the API supports pagination.

MinIO Community's repository is archived and its latest security release is distributed as source. The development image builds the pinned upstream release `RELEASE.2025-10-15T17-29-55Z`, following [upstream release instructions](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z). Production storage should use a maintained hosted service through the storage interface.
