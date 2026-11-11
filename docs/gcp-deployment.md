# Google Cloud deployment

Deployed 2026-10-25 to project `gen-lang-client-0362286623`.

Public URL: https://lifestory-biographer-1019141557914.us-east1.run.app

This is a fresh installation. Local accounts, interviews, and uploaded files were not migrated. Create an account on the cloud login page. Microphone permission is requested by the browser when voice mode starts.

## Resources

| Resource | Configuration |
|---|---|
| Cloud Run | `lifestory-biographer`, `us-east1`, 1 CPU / 1 GiB, 0 minimum / 2 maximum instances |
| Backend VM | `biographer-backend`, `us-east1-b`, `e2-standard-4`, 50 GB persistent disk |
| Network | `biographer`, subnet `biographer-east`, `10.42.0.0/24` |
| API | VM private address `10.42.0.10:8000`; no public API firewall rule |
| Cloud SQL | `biographer-db`, PostgreSQL 16, `db-custom-1-3840`, 20 GB with auto-growth |
| Databases | `biographer`, `biographer_interviews`, `temporal`, `temporal_visibility` |
| Media bucket | `gs://gen-lang-client-0362286623-biographer-media`, private with uniform access |
| Images | Artifact Registry `us-east1/biographer` |
| Runtime secret | `biographer-runtime-env`, readable by backend service account only |
| Auth secret | `biographer-auth`, readable by frontend service account only |

My Biographies, Style Lab, and Interview Studio are enabled. Screenplay and Cinema routes are disabled in the backend and frontend build. Local defaults still enable all modules.

Cloud SQL automated backups, point-in-time recovery, and deletion protection are enabled. SQL traffic uses Cloud SQL Auth Proxy. The VM runs the API, worker, Redis, ClamAV, and a PostgreSQL-backed Temporal server; it does not use Temporal's development server. This first deployment has a single backend VM and a zonal database, not high availability.

GCS uses the XML/S3 interoperability API with a dedicated storage service account's HMAC credentials, stored in Secret Manager. Browser uploads go directly to private GCS through short-lived signed URLs. CORS allows only the Cloud Run origin. GCS provides at-rest encryption; AWS-specific SSE headers are omitted. Missing-object deletion is treated as successful. No credentials are committed in the repository.

## Images and build records

- Initial deployment: Cloud Build `f2e897f1-72c2-4883-af8d-b47d000e1b1e`.
- Frontend image: `us-east1-docker.pkg.dev/gen-lang-client-0362286623/biographer/web:gcp-20261025`.
- Backend release: `us-east1-docker.pkg.dev/gen-lang-client-0362286623/biographer/api:gcp-20261025-2` (GCS deletion compatibility fix).
- `infrastructure/gcp/cloudbuild.yaml` builds API/worker and the three-module frontend.
- `infrastructure/gcp/backend.compose.yaml` and `backend-startup.sh` describe VM services and startup.

Google Cloud CLI was downloaded to `/private/tmp/lifestory-gcp-tools/google-cloud-sdk/bin/gcloud`. This temporary tools directory is not a permanent installation. Install the CLI normally before relying on it for long-term administration.

## Operations

Use the Google Cloud console or `gcloud` with the explicit project and region:

```sh
gcloud run services describe lifestory-biographer --project=gen-lang-client-0362286623 --region=us-east1
gcloud compute ssh biographer-backend --project=gen-lang-client-0362286623 --zone=us-east1-b --tunnel-through-iap
```

On the VM:

```sh
sudo docker ps
sudo docker logs --tail 100 biographer-cloud-worker-1
sudo docker logs --tail 100 biographer-cloud-api-1
```

Deployment files are in `/opt/biographer`. `runtime.env` is root-readable and fetched from Secret Manager on boot. Never print or copy it into issue trackers or source control.

To deploy a new backend version, build a uniquely tagged image, update both the checked-in compose/startup files and VM startup metadata, authenticate Docker to Artifact Registry using the VM's service account, and pull/recreate API and worker containers. Run required database migrations before enabling the new version. Do not blindly downgrade across incompatible schema changes.

To rotate Gemini/storage credentials, add a new version of `biographer-runtime-env`, then refresh the VM's environment and recreate API/worker containers. The frontend auth secret uses a pinned Secret Manager version; rotate by explicitly updating its Cloud Run revision. Set `AUTH_URL` and bucket CORS together when changing the public hostname.

The Compute Engine VM and Cloud SQL instance continue incurring charges while provisioned, even when no one visits the website. Cloud Run scaling to zero does not stop these charges. Model usage, storage, backups, and network traffic are billed separately. Stopping the VM stops interviews and processing; do not delete the database or bucket to pause the app.

## Verification boundaries

- Backend regression suite: 111 passed before rollout; 4 additional deletion tests passed.
- Real GCS multipart upload/list/complete, signed download, file download, replacement, and cleanup exercised with a disposable object.
- Public HTTPS registration, secure login, three-module navigation, biography creation, browser file upload, ClamAV/Temporal processing, Style Lab profile creation, and interviewer Markdown configuration passed in Chrome.
- Configured Gemini conversation and TTS model metadata endpoints both returned HTTP 200 from the deployed backend.
- No paid Gemini transcription, conversation generation, or voice output was invoked during deployment validation. Those remain subject to the project's Gemini quota and model availability.
- Test accounts and synthetic media are removed after verification. Local user data remains untouched.

## Interview template release — 2026-10-28

- API/worker and web images: `interview-templates-20261028` in the existing `biographer` Artifact Registry repository.
- Cloud Build: `fd3abe5a-a30c-49f4-9e31-a606dea69896`.
- Cloud Run revision: `lifestory-biographer-00006-b4f` (100% traffic).
- Adds recommended Markdown templates, a local template file picker, and user-assigned interviewer name precedence. No database migration required.
- VM startup metadata and checked-in backend configuration use the updated API image.
- Live verification passed: registration/login, three-module navigation, recommended catalog, multiple selections saved in configuration Markdown, assigned name, and upload control. No paid Gemini calls were made.

## Production Editor release — 2026-11-10

- Live Cloud Run revision: `lifestory-biographer-00007-x92` (100% traffic).
- Web image: `editor-release-20261110`; API/worker image: `editor-release-20261110-2`.
- Cloud Builds: `fe8555cf-e8b0-4219-8900-71ae394fe4ef` (web/API), `60b2684d-933b-4531-aaa5-eadc8b9539ae` (corrected API migration).
- Cloud SQL backup completed before migration (operation `f28f3ff1-615f-4f91-bd10-499800000026`). Main database is at Alembic `0009`; interview bootstrap completed.
- Migration 0008 now uses a frozen table definition rather than importing the current model, preventing duplicate columns when upgrading through 0009.
- Regular cloud accounts see My biographies, Style Lab, and Interview Studio. Owner access to shared Editor versions and published materials remains available. Screenplay/Cinema APIs enforce the Editor restriction server-side.
- Production Editor sees all five modules and all production projects. Editor identity remains separate from project ownership. Account-management/billing/security permissions are not granted.
- Local defaults remain unchanged: the cloud-specific `FILM_STUDIOS_EDITOR_ONLY` / `NEXT_PUBLIC_FILM_STUDIOS_EDITOR_ONLY` flags enable these restrictions only in the cloud deployment.
- VM compose configuration and startup metadata use the new backend image. Existing cloud data was preserved; local user records/media were not copied.
- Validation: backend suite 155 passed, 3 skipped; live Chrome checks verified regular-user navigation and API restrictions, Editor navigation and cross-user project access, opening project context across all studios, sharing an Editor version and owner review, eight recommended templates, and background assets.
- Synthetic project/account removed after testing. Final cloud counts: four accounts (including the provisioned Editor), two original projects. API health passed.
- No paid Gemini/video generation calls were made during release verification; provider output and quotas were not tested.

## Editor photo selection and notification release — 2026-11-10

- API/worker/web image tag: `editor-photos-20261110`; Cloud Build `766127b3-405d-450d-9d4d-58d4794726e6`.
- Cloud Run revision `lifestory-biographer-00008-l2t` receives 100% traffic. VM compose and startup metadata use the same release.
- Database backup completed (operation `ead3d045-394f-47ad-bcf5-3d1100000026`); Alembic migration `0010` applied; backend health passed.
- Cinema Studio now lets Editors choose ready uploaded pictures from the selected biography and its interviews without preselecting them in Screenplay Editor. Other projects remain excluded. Selected originals and crops are frozen with the video-generation attempt.
- Owner email notifications are queued transactionally when Editor versions, clip sets, or films are shared. Sender configuration uses `antongchen@gmail.com`. SMTP authentication was confirmed absent at rollout; emails remain queued until SMTP_PASSWORD is configured in the runtime secret and workers recreated.
- Local Cinema/Editor regression checks passed (23 existing tests plus the new photo-selection test); frontend build passed. Live Chrome checks passed regular-user/Editor navigation, cross-user project access, sharing and owner review, recommended templates, and backgrounds. No paid video/provider calls or real email delivery were tested.
- Temporary test account/project removed. Final counts remain four users and two original projects.
