# Biography, Style Lab and Interview Studio workflow

Updated November 2, 2026 for the local webapp.

1. **My Biographies:** create/open a biography and upload its materials. Under **Recording scripts**, prepare the recording collection if needed, then start transcription beside an uploaded audio/video file. Progress, stop/resume, deletion and transcript review remain available. Review words and speaker roles, approve and save the script. The existing TXT/JSON archive and database indexing workflow is retained.
2. **Style Lab:** configure an interviewer avatar, name and genre. Select recommended templates, upload local documents (including prior interviewer Markdown), and optionally select saved scripts and the speaker role to learn from. Save the configuration and its Markdown, or choose and preview an existing saved configuration. Click **Proceed to Interview Studio**.
3. **Interview Studio:** the selected configuration is carried into the page. Enter an interview title, authorize provider use and start the interview. Existing voice/text conversation, material uploads, pause/resume, review, approval and save flows remain available. Saved interviews can be opened directly here.

Existing recordings, profile-backed transcript collections, archive IDs, saved interviewer configurations and interviews are retained. Existing transcript URLs still work; new transcript links use the biography route. A project's transcription collection is created only when requested and repeated requests reuse an existing owned collection. No database migration is required.

Validation: 63 API tests passed; local production build passed. Mocked browser checks passed for template selection in Style Lab, biography transcription progress/stop/resume/review/deletion, and the saved-configuration handoff to an enabled Start interview action. Paid Gemini generation and live microphone conversation were not exercised during this reorganization.

## Default templates from the local folder

The root `templates/` folder is mounted read-only into the local API. Its Markdown, TXT, PDF and DOCX files appear alongside the three built-in recommendations in Style Lab. Add files and refresh the page to update the list; no rebuild is needed. Word/PDF previews contain extracted text, and downloads use Markdown rather than pretending to be original Word documents. Unreadable files show an error and cannot be selected. Selected text is copied into the saved configuration, so later folder edits do not alter existing interviewers. These local source documents remain Git-ignored and are not automatically deployed to GCP.
