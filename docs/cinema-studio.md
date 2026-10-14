# Cinema Studio

Select a screenplay from your account's dropdown, or use **Proceed to Cinema Studio** after the Screenplay Editor's final save. Cinema Studio pins that saved revision so subsequent source edits do not silently change video prompts. Save a new final revision and select it to create another production. The saved screenplay Markdown can also be downloaded here.

## Generate and review

1. Review the prompt beside each subsection. Edit the character/environment description for a new sequence, then the action, dialogue and camera instructions for each shot.
2. Confirm sending the prompt and selected photos to Veo. Press **Generate video clip**. Each new generation may incur provider charges.
3. From the second subsection onward, optionally check **Start from last frame of previous clip**. The immediately preceding clip must be generated successfully with its final frame available. It does not need approval to continue the sequence; every clip still needs preview and approval before final saving or stitching. The worker extracts its final decoded frame and sends that image with the next prompt; it copies the seed's character/environment description unchanged. Unchecking starts a new sequence. Visual identity is guided, not guaranteed by the model.
4. Selected photo materials from that subsection in Screenplay Editor appear as optional references; choose up to three. Files are decoded and normalized to PNG on the worker. Unsupported image combinations or provider restrictions produce a visible error; references are never silently dropped.
5. Watch the preview to the end, then mark it satisfied, or choose to edit its prompt or regenerate with the same prompt. Each attempt is retained. Regenerating an earlier clip makes dependent later clips stale until regenerated; independent sequences remain valid.

The model is `veo-3.1-generate-preview`, using server-side `GEMINI_API_KEY`. No browser key is needed. Output is currently one **8-second, 720p, 16:9 clip with audio per subsection**. The original 10/15-second screenplay target stays visible; no silent stretching or invented extra shots are applied. Consequently the assembled film may be shorter than the screenplay estimate.

## Save, download and assemble

After every current clip is approved, choose **Save approved clips to database and archive**. A background job writes a ZIP containing the clips in sequence plus a manifest of interview UID, screenplay revision, subsection IDs, prompts, continuity links, actual durations and checksums. Video files live in object storage; PostgreSQL stores their provenance, locations and approvals.

Download the ZIP, or use **Save clips to a local folder** in a browser supporting the File System Access API. The folder picker requires your browser permission. Other browsers can extract the ZIP into any chosen folder. Nothing silently writes to an arbitrary local path.

Then choose whether to stitch. FFmpeg normalizes resolution/frame rate/audio and concatenates the approved clips in screenplay order, retaining existing audio and adding silence only for clips with no audio track. Preview and download the assembled MP4. Existing archives are immutable; new clip attempts require a newly approved collection.

## Persistence and operation recovery

Migration `i0005` adds `cinema_productions` and `cinema_jobs` to the separate interview PostgreSQL database. API actions are owner scoped, and production locks prevent duplicate concurrent submissions for a subsection. Temporal dispatches clip, archive and stitching jobs. Status persists across reloads. Veo does not expose a completion percentage, so the UI shows a stage and indeterminate progress indicator.

The provider operation ID is persisted immediately after submission. A failed job with an operation can be resumed without making another paid generation request. An interruption between provider acceptance and saving its operation ID is explicitly marked ambiguous and never automatically resubmitted: check Gemini usage before requesting another generation. Screenplays used by a production are protected from deletion to retain their provenance and material references.

Provider API reference: https://ai.google.dev/gemini-api/docs/veo

Validation uses mocked provider responses, actual FFmpeg extraction/stitching, database/API tests and browser checks. Live Veo output quality, account quotas and acceptance of particular image combinations require an explicitly initiated generation in the UI.
