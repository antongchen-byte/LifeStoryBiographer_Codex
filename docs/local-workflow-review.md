# Local workflow review

Reviewed November 1, 2026. All five modules are retained. Changes apply to the local application; no GitHub push or GCP deployment was performed.

## Findings and changes

| Module | Workflow issue | Resolution |
| --- | --- | --- |
| My Biographies | Shared media controls must remain appropriate for general project assets. | Retained general upload, search, preview and asset management. Template-only filtering applies only in Interview Studio. |
| Style Lab | Processing needs explicit start, persistent progress, stop/resume and review destinations. | Reviewed the existing controls and verified the processing workflow with the browser fixture. No core processing feature removed. |
| Interview Studio | Uploaded templates appeared in two lists, while irrelevant photo/video categories distracted from document selection. | Consolidated template selection onto document cards; restricted this view to supported document types and removed irrelevant category tabs. |
| Interview Studio | Changing references after saving a configuration could start an interview with the older configuration. | Added a changed-settings notice and require saving configuration changes before starting. A custom interviewer name can still be applied directly. |
| Interview Studio | A newly cloned custom-name configuration could leave the old configuration selected. | Select the returned configuration and refresh the saved configuration list after starting. |
| Interview Studio | Database implementation terminology obscured user actions. | Replaced PostgreSQL-oriented labels with plain saved-script and conversation labels. |
| Screenplay Editor | Leaving the page could discard unsaved edits without warning. | Added reload/close and navigation-link warnings, complementing the existing source-switch check. |
| Cinema Studio | Unfinalized screenplays were selectable and led to failed loading without a clear preparation step. | Mark readiness in the listing, disable unfinalized choices, and link to Screenplay Editor. Backend validation remains authoritative. |
| Cinema Studio | Provider consent carried over when switching screenplays. | Reset consent when a different screenplay is loaded. |
| Cinema Studio | Planned duration could appear to be a measured clip duration before generation. | Distinguish planned seconds, actual measured duration, and absence of a completed clip. |
| Cinema Studio | Replacing a completed clip could start another paid generation too easily. | Confirm replacement generation and explain the new review requirement; retain the previous version. |
| Cinema Studio | Archive creation was described as saving clips to the database, although clips were already persisted. Repeated archive actions were redundant. | Rename the action to preparing approved clips for download and disable it once the current archive is ready. |
| Cinema Studio | Switching screenplays or leaving could silently discard unsubmitted prompt/reference edits. | Warn on screenplay switching, navigation links and reload/close; clear the corresponding dirty marker after successful submission. |

Existing recordings, interviews, scripts, photos and clips are preserved. The 48-second screenplay sections and 4-, 6- or 8-second video subdivisions remain available. Existing timing fixtures were updated to these choices.

## Validation

- Full backend suite: **140 passed, 3 skipped**, with two deprecation warnings.
- Targeted interview, screenplay, cinema and Omni suite: **57 passed**.
- Production Next.js build and TypeScript checks passed; the local web container was rebuilt and restarted.
- Interview Studio browser fixture passed: recommended-template defaults and multiselect, preview, native file picker, unified document selection, saved configuration payload, changed-configuration warning, and mobile overflow check.
- Style Lab browser fixture passed: processing controls, progress, stop/resume, deletion and transcript destination.
- Cinema Studio browser fixture passed: unfinalized choices disabled, preparation link visible, and provider consent reset when switching screenplays.
- `git diff --check` passed.

## Limits and remaining considerations

This is a code review plus automated fixture validation, not proof that every possible workflow is correct. Browser fixtures use mocked APIs and do not alter existing user records. The complete existing screenplay/cinema end-to-end suites were not run. No paid Gemini/Omni generation or live microphone conversation was initiated during this review. Three backend integration tests were skipped.

Omni's requested clip duration is not guaranteed by the provider; the UI reports measured duration after completion. Unsaved-edit guards cover page close/reload, navigation links and explicit source switching; browser-history navigation is not separately verified. No entire module was removed.
