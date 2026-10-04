Build this as an interview application with two inputs: **recorded interviews that establish how to interview**, and **reference questions that establish what to cover**. The chatbot should adapt its wording and follow-ups while tracking coverage explicitly.

For the first release, I recommend a text-based interviewing interface with audio/video upload for learning the interviewer’s style. Live voice can follow once the interview behavior works reliably.

**1. Define the core workflow**

The interviewer:

1. Creates an interviewer profile.
2. Uploads recordings and reference questions.
3. Reviews the extracted style, interviewing patterns, and question plan.
4. Runs a practice interview and adjusts the results.
5. Publishes a version that can be used for new interviews.

Each new interview uses a fixed version of that configuration. Later edits apply to future interviews, avoiding unexpected behavior changes during an active session.

The interviewee receives an introduction, answers questions conversationally, and can skip a question, correct an answer, or end the interview. At completion, the application produces a summary and a coverage report.

**2. Convert reference questions into a structured interview plan**

Support TXT, DOCX, and text-based PDF uploads, plus direct entry. Flag scanned PDFs for OCR or manual entry rather than silently importing an empty question set.

The system extracts questions into editable records:

| Field | Purpose |
|---|---|
| `id` | Stable identifier |
| `original_text` | Preserve the uploaded wording |
| `intent` | What the interviewer wants to learn |
| `topic` | Group related questions |
| `priority` | Required, recommended, or optional |
| `wording_mode` | Exact wording or flexible paraphrase |
| `coverage_criteria` | Information needed to consider it answered |
| `dependencies` | Questions that should come first |
| `applicability_rule` | When this question applies |
| `follow_up_guidance` | Useful probes and depth limits |
| `source_reference` | File and location where it originated |

Default to flexible wording and recommended priority; require the interviewer to review inferred priorities, conditions, and coverage criteria.

For example:

> Reference question: “Who influenced you most during childhood, and how?”

The coverage criteria might be: identify a person and describe their influence. Naming someone alone would count as a partial answer. A concrete memory could be an optional follow-up.

Detect duplicate questions and suggest consolidation, but preserve them until the interviewer accepts the change. Validate dependencies to prevent circular ordering.

**3. Process recordings into a reviewed style profile**

Use background jobs to:

1. Extract audio when necessary.
2. Transcribe with speaker labels and timestamps.
3. Let the interviewer identify the correct speaker and fix important transcript errors.
4. Annotate question types, acknowledgments, probes, transitions, and closing behavior.
5. Compare recordings to identify recurring patterns.
6. Generate a draft style profile and example library.

Each pattern should store its source timestamps, supporting exchanges, confidence, and review status. Only approved patterns enter the published profile.

The resulting profile should describe observable behavior, such as:

> Ask one main question at a time. Use brief acknowledgments. When an answer is abstract, invite a specific example. Before changing topics, connect the transition to something the participant said.

Keep source-specific facts out of the general profile. Treat explanations of the interviewer’s intentions as hypotheses until confirmed.

**4. Track coverage separately from conversational style**

A question being asked does not mean it was answered. Maintain two independent fields:

| Dimension | Values |
|---|---|
| Coverage | Not covered, partially covered, covered |
| Disposition | Active, declined, not applicable, deferred |

For each question, store supporting interviewee turn IDs, a concise explanation, and any missing information.

This allows the chatbot to recognize that one answer covered several questions, or that a required question was explicitly declined. “Required” means the chatbot should attempt coverage; it does not override the interviewee’s choice.

Coverage assessment should follow these rules:

- Count information volunteered elsewhere in the conversation.
- Require evidence from the current interviewee’s answers.
- Never infer coverage merely because the chatbot asked a question.
- Reassess affected coverage after a correction or retraction.
- Keep uncertain cases partial and clarify naturally.
- For exact-wording questions, track whether the wording was delivered separately from whether the information was obtained.

At closing, report unresolved required questions and their reasons.

**5. Implement a controlled conversation loop**

Use the application to enforce question eligibility and state changes. Let the language model interpret answers and propose conversational moves.

For each interviewee message:

1. **Save the turn** using an idempotent request ID.
2. **Analyze the answer** for relevant facts, coverage evidence, corrections, boundaries, and possible follow-ups.
3. **Validate proposed updates** against known question IDs and actual transcript evidence.
4. **Choose the next move** from acknowledge, clarify, probe, ask a reference question, transition, or close.
5. **Retrieve style examples** relevant to that move.
6. **Generate the response** using the approved profile, current context, and selected question.
7. **Check the result** for duplicate questions, unsupported assumptions, exact-wording requirements, and boundary violations.
8. **Save and deliver the response**, recording the configuration version and selected action.

Use this decision order:

- Respond to a request to stop, skip, or correct.
- Resolve a clarification necessary to understand the answer.
- Follow a useful thread within the configured depth limit.
- Address eligible required questions.
- Address recommended and optional questions as time permits.
- Close with a brief opportunity for additions.

Use configurable limits for follow-ups and interview duration. Avoid exhausting the available time on early questions.

To preserve spontaneity, treat the reference questions as a coverage plan rather than a fixed script, except where ordering or wording is explicitly required.

**6. Store the application state in these entities**

| Entity | Main contents |
|---|---|
| `interviewer_profiles` | Ownership and profile metadata |
| `source_assets` | Recording/question files, permissions, processing status |
| `transcript_turns` | Speaker, text, timestamps, source |
| `style_versions` | Approved instructions and publication status |
| `style_examples` | Annotated exchanges, context, embeddings, provenance |
| `question_set_versions` | Versioned questions and coverage criteria |
| `interview_config_versions` | Style version, question-set version, runtime settings |
| `interview_sessions` | Participant, configuration version, status |
| `session_turns` | Ordered interview messages |
| `session_question_states` | Coverage, disposition, evidence, gaps |
| `session_memories` | Current participant facts and unfinished threads |
| `evaluation_runs` | Test configuration, results, reviewer feedback |

Use a relational database for authoritative records, object storage for recordings and documents, and an optional vector index for example retrieval. A small initial example library can use tagged retrieval before adding embeddings.

Keep private source material and participant memories scoped to their owners and sessions. Shared style examples should be reviewed and anonymized. Uploaded documents and transcripts must be treated as data, never as application instructions.

**7. Define the service boundaries**

A provider-neutral implementation needs:

- **Web application:** upload, review, configuration, practice, interview, and reporting screens.
- **API service:** authentication, versioning, session state, and conversation orchestration.
- **Background worker:** transcription, document extraction, style analysis, and report generation.
- **Model adapters:** transcription, structured analysis, response generation, and optional embeddings.
- **Storage:** relational database plus protected object storage.

Minimum API operations:

| Operation | Endpoint |
|---|---|
| Create profile | `POST /profiles` |
| Register upload and processing job | `POST /profiles/{id}/assets` |
| Inspect processing progress | `GET /jobs/{id}` |
| Review/edit style draft | `PATCH /profiles/{id}/style-drafts/{draftId}` |
| Review/edit question draft | `PATCH /question-sets/{id}/draft` |
| Publish validated configuration | `POST /interview-configs/{id}/versions` |
| Start interview | `POST /sessions` |
| Submit answer and receive next response | `POST /sessions/{id}/turns` |
| Resume interview | `GET /sessions/{id}` |
| End interview | `POST /sessions/{id}/complete` |
| Retrieve summary and coverage | `GET /sessions/{id}/report` |

Serialize turn processing per session to prevent overlapping requests from producing duplicate questions. Retry failed processing jobs without duplicating records.

**8. Build in five milestones**

| Milestone | Deliverable | Acceptance condition |
|---|---|---|
| 1. Intake and questions | Uploads, processing jobs, question editor, versioning | Every approved question retains its source and validated fields |
| 2. Style extraction | Reviewed transcript, profile, example library | Published style rules trace back to approved evidence |
| 3. Interview engine | Conversation loop, session memory, coverage tracking | Handles volunteered answers, partial answers, skips, corrections, and resume |
| 4. Review and reporting | Practice mode, interviewer feedback, final report | Coverage links to transcript evidence; missing items are explicit |
| 5. Pilot and refinement | Evaluations and interviews with new participants | Meets agreed quality targets before broader release |

Fine-tuning is outside the first release. Add it only if reviewed instructions and examples repeatedly fail to produce the desired behavior.

**9. Establish the release tests before implementation**

Create a fixed evaluation set covering:

- One answer satisfies multiple reference questions.
- A question is asked but receives no substantive answer.
- The participant partially answers a compound question.
- The participant declines a required question.
- A later correction invalidates earlier coverage.
- A conditional question becomes inapplicable.
- An exact-wording question must still be delivered.
- The participant goes off topic or supplies very short answers.
- Time runs short with required questions remaining.
- The session resumes after interruption.
- An uploaded document contains instructions attempting to override the application.
- Private details from another interview must not appear.

Measure coverage precision and recall against human annotations, repeated-question rate, appropriate handling of boundaries, and interviewer-rated style fidelity. Keep whole interviews and interviewees out of the development examples for final evaluation.

The first implementation should make every next-question decision and coverage judgment inspectable. That gives the interviewer a concrete way to correct both **what the chatbot covers** and **how it conducts the conversation**.