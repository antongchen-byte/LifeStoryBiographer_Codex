Below is an implementation-ready architecture and a Codex specification that I would use as the starting point for the product.

# AI Biographer

## Software Architecture and Codex Implementation Specification

**Version:** 1.0
**Target:** Production-capable MVP evolving into a multi-user SaaS platform
**Primary AI stack:** Google Gemini + Gemini Live + Veo
**Primary workflow:** Style Lab → Interview Studio → Screenplay Editor → Cinema Studio

---

# 1. Product Vision

AI Biographer is a multimodal web application that helps a person transform memories, interviews, photographs, home videos, recordings, letters, and other personal materials into a professionally structured biographical film.

The system acts as four related tools:

1. **Style Lab**

   * Learns how accomplished interviewers conduct interviews.
   * Processes example interviews from video, audio, transcripts, documents, and text.
   * Extracts interviewing patterns rather than merely copying wording.

2. **Interview Studio**

   * Conducts conversational biographical interviews through voice and text.
   * Records sessions.
   * Creates transcripts.
   * Builds a structured understanding of the person's life.
   * Collects photographs, video, audio, documents, and other supporting evidence.
   * Dynamically determines what questions to ask next.

3. **Screenplay Editor**

   * Turns selected life stories into chapters, sequences, scenes, and shots.
   * Grounds scripts in interview evidence and uploaded materials.
   * Gives a human editor and biography subject control before video generation.

4. **Cinema Studio**

   * Generates video shots.
   * Uses source photographs/video whenever available.
   * Maintains visual, character, period, location, narration, and genre continuity.
   * Assembles generated and uploaded material into a finished biographical film.

The underlying design principle is:

> **AI proposes; humans curate; provenance remains traceable.**

---

# 2. High-Level Architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                       WEB APPLICATION                         │
│                                                              │
│  Dashboard                                                   │
│      │                                                       │
│      ├── Style Lab                                           │
│      ├── Interview Studio                                    │
│      ├── Screenplay Editor                                   │
│      └── Cinema Studio                                       │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTPS / WebSocket
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                       API GATEWAY                             │
│ Authentication • Authorization • Rate Limits • Audit         │
└────────────────────────┬─────────────────────────────────────┘
                         │
       ┌─────────────────┼────────────────────────────┐
       ▼                 ▼                            ▼
┌──────────────┐ ┌────────────────┐          ┌─────────────────┐
│ Biography    │ │ AI             │          │ Media           │
│ Service      │ │ Orchestrator   │          │ Service         │
└──────┬───────┘ └──────┬─────────┘          └────────┬────────┘
       │                │                             │
       │       ┌────────┼───────────────┐             │
       │       ▼        ▼               ▼             │
       │    Gemini   Gemini Live       Veo            │
       │
       ▼                                                 ▼
┌─────────────────┐                            ┌────────────────┐
│ PostgreSQL      │                            │ Object Storage │
│ + pgvector      │                            │ GCS/S3        │
└─────────────────┘                            └────────────────┘
       │                                                 │
       └───────────────┬─────────────────────────────────┘
                       ▼
             ┌────────────────────┐
             │ Workflow Engine    │
             │ Temporal           │
             └─────────┬──────────┘
                       ▼
          ┌──────────────────────────┐
          │ Background Media Workers │
          │ FFmpeg • Transcoding     │
          │ Thumbnails • Rendering   │
          │ Audio extraction         │
          │ Video assembly           │
          └──────────────────────────┘
```

---

# 3. Recommended Technology Stack

## Frontend

Use:

* **Next.js**
* React
* TypeScript
* Tailwind CSS
* shadcn/ui
* TanStack Query
* Zustand for local editor state
* WebSocket/WebRTC support
* WaveSurfer.js for audio visualization
* TipTap for screenplay editing
* Remotion player or custom HTML5 video timeline
* Uppy or similar resumable uploader

Suggested structure:

```text
apps/
  web/
    app/
      dashboard/
      style-lab/
      interview/
      screenplay/
      cinema/
```

---

# 4. Backend Architecture

I recommend separating interactive application traffic from computational media processing.

### Web/API backend

**FastAPI/Python**

Advantages:

* excellent Gemini SDK integration;
* natural integration with AI/media workflows;
* Pydantic schemas;
* async WebSocket support;
* strong ecosystem for ML and multimedia processing.

### Background jobs

Use:

* Temporal
* Python workers
* FFmpeg
* optional GPU worker pool

Avoid implementing long-running generation jobs directly in HTTP request handlers.

Example:

```text
POST /api/scenes/{sceneId}/generate

       ↓

create generation_job

       ↓

Temporal workflow

       ↓

Gemini prompt preparation

       ↓

Veo generation

       ↓

download generated asset

       ↓

store asset

       ↓

run QC

       ↓

update scene

       ↓

notify frontend
```

---

# 5. Storage Layer

## PostgreSQL

Use PostgreSQL for:

* users;
* biography projects;
* interviews;
* transcript segments;
* life events;
* people;
* places;
* screenplay versions;
* scenes;
* shots;
* media metadata;
* generated assets;
* approval state;
* audit trail.

Enable:

```text
pgvector
```

for semantic retrieval.

---

# 6. Object Storage

Use Google Cloud Storage or S3-compatible storage.

Example:

```text
/projects/{project_id}/

    originals/
        interviews/
        images/
        audio/
        video/
        documents/

    processed/
        audio/
        video-proxies/
        thumbnails/
        transcripts/

    screenplay/

    generation/
        scene-001/
        scene-002/

    renders/
        drafts/
        final/
```

Do **not** treat Gemini Files as permanent project storage.

Gemini Files supports multimodal uploads, including video, audio, documents and images, but Google's current documentation states uploaded files are automatically deleted after 48 hours. ([Google AI for Developers][1])

---

# 7. Core Domain Model

The application's most important conceptual distinction should be:

```text
PERSON
   │
BIOGRAPHY PROJECT
   │
LIFE CHAPTER
   │
STORY
   │
EVENT
   │
SCREENPLAY SEQUENCE
   │
SCENE
   │
SHOT
```

This avoids treating the biography as one giant conversation.

---

# 8. Core Database Objects

## Project

```typescript
interface BiographyProject {
  id: string;
  ownerId: string;

  subjectName: string;
  title?: string;

  defaultLanguage: string;

  status:
    | "intake"
    | "story_development"
    | "screenplay"
    | "production"
    | "completed";

  createdAt: string;
  updatedAt: string;
}
```

---

## LifeChapter

```typescript
interface LifeChapter {
  id: string;
  projectId: string;

  title: string;
  summary: string;

  approximateStartDate?: string;
  approximateEndDate?: string;

  order: number;
}
```

Examples:

```text
Childhood in Sevastopol
University Years
Coming to America
Early Career
Family
Later Life
Reflections
```

The system must allow nonlinear storytelling.

---

# 9. Life Event

```typescript
interface LifeEvent {
  id: string;
  projectId: string;
  chapterId?: string;

  title: string;
  description: string;

  startDate?: string;
  endDate?: string;

  location?: LocationRef[];

  people?: PersonRef[];

  emotionalTone?: string[];

  themes?: string[];

  sourceIds: string[];

  certainty:
    | "verified"
    | "subject-recalled"
    | "inferred"
    | "uncertain";
}
```

This becomes the factual backbone of the biography.

---

# 10. Evidence / Provenance Model

Every meaningful factual statement should retain its source.

Example:

```typescript
interface Evidence {
  id: string;

  projectId: string;

  sourceType:
    | "interview"
    | "document"
    | "photo"
    | "video"
    | "audio"
    | "manual";

  sourceId: string;

  transcriptStartMs?: number;
  transcriptEndMs?: number;

  quote?: string;

  confidence?: number;
}
```

A screenplay sentence should therefore be traceable:

```text
"The family moved to Philadelphia in 1987."

Evidence:
Interview #4
00:18:22 → 00:18:39
```

This feature will dramatically improve editorial trust.

---

# 11. Component A — Style Lab

## Objective

Learn **interview methodology** rather than simply reproducing a journalist's sentences.

User inputs may include:

```text
.mp4
.mov
.mpeg
.mpg
.webm
.m4v
.mp3
.wav
.m4a
.aac
.txt
.md
.docx
.pdf
```

---

# 12. Style Lab Processing Pipeline

```text
Upload
   ↓
MIME validation
   ↓
Virus/security scan
   ↓
Store original
   ↓
Transcode when required
   ↓
Extract audio
   ↓
Speech/transcript processing
   ↓
Speaker identification
   ↓
Turn segmentation
   ↓
Question/answer classification
   ↓
Interview strategy analysis
   ↓
Style profile
   ↓
Human review
```

Gemini can consume multimodal files including audio, video, text and images, making it useful for this analysis stage. ([Google AI for Developers][1])

---

# 13. Interview Style Model

Do not represent style as one prompt.

Create a structured `InterviewStyleProfile`.

```typescript
interface InterviewStyleProfile {

  name: string;

  tone: {
    warmth: number;
    formality: number;
    curiosity: number;
    directness: number;
    humor: number;
  };

  questionPatterns: {
    openEndedRatio: number;
    followUpRatio: number;
    reflectiveRatio: number;
    factualRatio: number;
  };

  techniques: string[];

  pacing: {
    averageQuestionLength: number;
    questionsBeforeTopicShift: number;
  };

  emotionalBehavior: {
    handlesSilence: string;
    handlesEmotion: string;
    handlesTrauma: string;
  };

  openingPatterns: string[];

  followUpPatterns: string[];

  transitionPatterns: string[];

  avoidedPatterns: string[];
}
```

---

# 14. Interview Technique Extraction

Gemini analyzes transcripts using structured output.

For each interviewer turn:

```json
{
  "question": "What do you remember most about that summer?",
  "type": "episodic_memory",
  "technique": "open_ended_recall",
  "tone": ["warm", "curious"],
  "follow_up_to": "previous answer",
  "purpose": "elicit sensory memories",
  "specificity": 0.32,
  "emotional_pressure": 0.08
}
```

Gemini supports JSON-schema-constrained structured output, which is appropriate for extracting these machine-readable interview characteristics. ([Google AI for Developers][2])

---

# 15. Style Learning Strategy

The first version should **not fine-tune a model**.

Instead:

```text
Example interviews
        ↓
Extract techniques
        ↓
Create style vectors
        ↓
Create Style Profile
        ↓
Store representative interview examples
        ↓
RAG retrieval
        ↓
Dynamic interviewer instructions
```

This provides:

* controllability;
* attribution;
* rapid iteration;
* easier deletion;
* multiple selectable interviewer styles.

Example user selection:

```text
Interview Style

○ Gentle memoirist
○ Investigative journalist
○ Documentary filmmaker
○ Family historian
○ Custom: "Barbara interview collection"
```

---

# 16. Component B — Interview Studio

The Interview Studio should feel like talking with an accomplished biographer, not completing a questionnaire.

Two operating modes:

```text
TEXT MODE

VOICE MODE
```

The user may switch modes without losing context.

---

# 17. Voice Architecture

Gemini Live is appropriate for the interactive voice experience because it supports continuous audio/text input, native audio output, transcripts, interruption/barge-in and WebSocket-based sessions. Google's documentation currently describes the Live API as Preview, so the implementation should isolate it behind a provider interface rather than tightly coupling the product to a preview API. ([Google AI for Developers][3])

Architecture:

```text
Browser microphone

      ↓

AudioWorklet

      ↓

PCM stream

      ↓

Gemini Live WebSocket

      ↓

AI interviewer

      ↓

audio response

      ↓

browser speakers
```

For production, use ephemeral authentication for direct browser connections rather than exposing permanent API keys. Google's Live API documentation recommends ephemeral tokens for production client-to-server implementations. ([Google AI for Developers][3])

---

# 18. Interview Session State

The AI interviewer needs an explicit state machine.

```text
START
  ↓
RAPPORT
  ↓
STORY_SELECTION
  ↓
ORIENTATION
  ↓
MEMORY_EXPLORATION
  ↓
DEEPENING
  ↓
MEDIA_DISCOVERY
  ↓
REFLECTION
  ↓
GAP_CHECK
  ↓
SUMMARY
  ↓
CONTINUE / END
```

The LLM should recommend transitions.

Application code controls them.

Do not allow the model alone to determine application state.

---

# 19. Interview Director Agent

Introduce an invisible supervisory agent:

```text
INTERVIEWER
     ↑
     │ instructions
     │
INTERVIEW DIRECTOR
```

The user communicates with the Interviewer.

The Director silently evaluates:

```text
What have we learned?

What is missing?

What deserves a follow-up?

Has the person become emotional?

Are we repeating ourselves?

Is chronology unclear?

Who else should we ask about?

Is supporting media likely to exist?

Should we stay here or move forward?
```

Director output:

```json
{
  "state": "MEMORY_EXPLORATION",
  "coverage": 0.68,
  "recommended_action": "follow_up",
  "question_goal": "understand relationship with father",
  "suggest_media_request": false,
  "sensitivity": "medium"
}
```

---

# 20. Biography Knowledge Graph

As interviews accumulate, construct:

```text
Albert
  │
  ├── PERSON → Mother
  ├── PERSON → Father
  ├── LIVED_IN → Philadelphia
  ├── VISITED → Virginia Beach
  └── EVENT → Family vacation

EVENT
  ├── WHEN
  ├── WHERE
  ├── WHO
  ├── WHAT
  ├── WHY
  ├── EMOTION
  ├── MEDIA
  └── EVIDENCE
```

For MVP this can remain in PostgreSQL rather than introducing Neo4j.

---

# 21. Dynamic Question Planning

Before producing the next question:

```python
context = retrieve(
    current_story,
    recent_turns,
    unresolved_questions,
    relevant_life_events,
    interview_style,
    known_people,
    existing_media
)

director_decision = interview_director(context)

question = interviewer.generate(
    director_decision,
    interview_style
)
```

This avoids passing the entire biography into every model call.

---

# 22. Media Collection During Interview

At any time the interviewer may say:

> "Do you happen to have a photograph from that apartment?"

User can:

```text
Upload photo
Upload video
Upload audio
Upload document
Take photo
Skip
```

The interview continues independently of processing.

---

# 23. Media Asset Model

```typescript
interface MediaAsset {

  id: string;
  projectId: string;

  type:
    | "image"
    | "video"
    | "audio"
    | "document";

  originalFilename: string;

  storageUri: string;

  mimeType: string;

  durationMs?: number;

  width?: number;
  height?: number;

  capturedAt?: string;

  location?: string;

  people?: string[];

  description?: string;

  linkedEventIds: string[];

  processingStatus:
    | "uploaded"
    | "processing"
    | "ready"
    | "failed";
}
```

---

# 24. Interview Completion Pipeline

At session end:

```text
raw recording
      ↓
transcript
      ↓
speaker turns
      ↓
story segmentation
      ↓
entity extraction
      ↓
event extraction
      ↓
timeline update
      ↓
relationship update
      ↓
story summaries
      ↓
missing-information analysis
```

The user sees:

```text
Today's Stories

✓ First day at university
✓ Meeting Nina
✓ Summer trips home

Possible follow-ups

○ What happened immediately after graduation?
○ Do you have the photograph of the apartment?
○ Who painted the sea painting?
```

---

# 25. Component C — Screenplay Editor

The Screenplay Editor transforms **story evidence** into cinematic structure.

Hierarchy:

```text
Biography
   ↓
Chapter
   ↓
Sequence
   ↓
Scene
   ↓
Shot
```

---

# 26. Screenplay Generation

Gemini produces structured screenplay JSON.

```typescript
interface ScreenplayScene {

  id: string;

  title: string;

  durationTargetSeconds: number;

  narrativePurpose: string;

  narration?: string;

  dialogue?: DialogueLine[];

  location: string;

  period: string;

  characters: CharacterRef[];

  visualDescription: string;

  emotionalTone: string[];

  sourceAssets: string[];

  evidenceIds: string[];

  shots: ShotSpec[];
}
```

---

# 27. Shot Specification

```typescript
interface ShotSpec {

  shotNumber: number;

  durationSeconds: number;

  shotType:
    | "establishing"
    | "wide"
    | "medium"
    | "closeup"
    | "insert"
    | "montage";

  action: string;

  cameraMovement?: string;

  composition: string;

  visualPrompt: string;

  audioPrompt?: string;

  dialogue?: string;

  narration?: string;

  sourceAssetIds: string[];

  continuityConstraints: string[];
}
```

---

# 28. Thirty-Second Scene Rule

Your editor should treat **30 seconds as a screenplay/editorial unit rather than one generation request**.

Current Veo 3.1 documentation describes generation of 8-second videos. Therefore:

```text
Screenplay sequence = up to ~30 sec

Shot 1 = 8 sec
Shot 2 = 8 sec
Shot 3 = 8 sec
Shot 4 = 4–8 sec

             ↓

Cinema Studio

             ↓

assembled sequence
```

Veo also currently supports capabilities including reference-image guidance, first/last-frame control and video extension, which are particularly useful for maintaining visual continuity between shots. ([Google AI for Developers][4])

---

# 29. Screenplay Editor UI

Three-column interface:

```text
┌────────────────┬─────────────────────────┬──────────────────┐
│ STORY          │ SCREENPLAY              │ MEDIA            │
│                │                         │                  │
│ Childhood      │ Scene 12                │ Photos           │
│ University     │                         │ Video            │
│ America        │ INT. APARTMENT - DAY   │ Audio            │
│ Career         │                         │ Documents        │
│ Family         │ Narration...            │ Generated        │
│                │                         │                  │
└────────────────┴─────────────────────────┴──────────────────┘
```

Editor operations:

```text
Rewrite
Shorten
Expand
Split scene
Merge scenes
Change POV
Change tone
Attach photo
Attach video
Generate storyboard
Approve
Lock
```

---

# 30. Screenplay Versioning

Never overwrite approved text.

```text
Scene v1 — AI draft

Scene v2 — editor revision

Scene v3 — subject revision

Scene v4 — approved

LOCKED
```

Implement:

```text
screenplay_versions
scene_versions
```

with parent version IDs.

---

# 31. Component D — Cinema Studio

This is the production system.

Responsibilities:

```text
shot generation
asset management
continuity
voiceover
music
sound effects
captions
timeline editing
shot replacement
color consistency
final rendering
```

---

# 32. Continuity Bible

One of the most important components of the product.

Every biography project gets a machine-readable:

```text
CONTINUITY BIBLE
```

Example:

```json
{
  "genre": "cinematic autobiographical documentary",

  "visual_language": {
    "lens": "natural documentary",
    "camera": "slow restrained movement",
    "lighting": "naturalistic",
    "grain": "subtle film grain"
  },

  "character_rules": {
    "young_nina": {
      "age": 22,
      "hair": "dark brown",
      "references": ["asset-123"]
    }
  },

  "location_rules": {
    "childhood_apartment": {
      "reference_assets": ["asset-54", "asset-89"],
      "walls": "pale gray",
      "windows": "large south facing"
    }
  },

  "period_rules": {
    "1970s_ussr": {
      "cars": "...",
      "clothing": "...",
      "architecture": "..."
    }
  }
}
```

Every video generation request incorporates the relevant subset.

---

# 33. Character Identity Pack

For recurring people create:

```text
CHARACTER PACK

Name
Age in scene
Reference photographs
Hair
Face
Body
Clothing
Accessories
Voice
Movement
Relationship
Period-specific appearance
```

Veo's reference-image functionality should be exploited whenever source material permits it. Current Veo 3.1 documentation supports up to three reference images for guiding generation. ([Google AI for Developers][4])

---

# 34. Location Pack

Likewise:

```text
LOCATION PACK

Location
Time period
Architecture
Furniture
Weather
Lighting
Reference images
Allowed modifications
Forbidden elements
```

Example forbidden element:

```text
1958 Sevastopol waterfront:

DO NOT INCLUDE:
modern cars
smartphones
modern skyscrapers
LED signage
contemporary clothing
```

---

# 35. Scene Generation Workflow

```text
Approved screenplay

       ↓

Shot Planner

       ↓

Continuity Resolver

       ↓

Reference Asset Selector

       ↓

Prompt Composer

       ↓

Veo

       ↓

Generated clip

       ↓

Automated QC

       ↓

Human review

      ┌┴─────────────┐
      │              │
    Accept        Regenerate
      │
      ▼
Timeline
```

---

# 36. Generation Provider Abstraction

Do not hard-code Veo throughout the application.

```typescript
interface VideoGenerationProvider {

  generate(
    request: VideoGenerationRequest
  ): Promise<GenerationJob>;

  getStatus(
    jobId: string
  ): Promise<GenerationStatus>;

  extend?(
    assetId: string,
    request: ExtensionRequest
  ): Promise<GenerationJob>;
}
```

Implementation:

```text
providers/
    veo.ts
```

Future implementations could include other approved video providers without changing the domain layer.

---

# 37. Automated Clip QC

Every generated clip should be evaluated before presentation.

Check:

```text
Character identity
Number of characters
Era consistency
Location consistency
Major objects
Motion
Prompt adherence
Dialogue
Visual artifacts
Continuity
Safety
```

Generate:

```json
{
  "overallScore": 0.86,

  "identityConsistency": 0.91,
  "periodConsistency": 0.97,
  "promptAlignment": 0.82,

  "issues": [
    "coat color differs from previous shot"
  ],

  "recommendation": "accept_with_warning"
}
```

---

# 38. Timeline Model

```typescript
interface TimelineItem {

  id: string;

  track:
    | "video"
    | "voiceover"
    | "dialogue"
    | "music"
    | "ambient"
    | "caption";

  sourceAssetId: string;

  startMs: number;
  endMs: number;

  sourceStartMs?: number;
  sourceEndMs?: number;

  volume?: number;
  transitionIn?: string;
  transitionOut?: string;
}
```

---

# 39. Cinema Studio UI

```text
PREVIEW

┌───────────────────────────────────────────┐
│                                           │
│                 VIDEO                     │
│                                           │
└───────────────────────────────────────────┘


STORYBOARD

[001] [002] [003] [004] [005]


TIMELINE

VIDEO    ███████████████████████

VOICE       █████ █████████

MUSIC    ███████████████████████

CAPTION     █████ █████ █████
```

Operations:

```text
generate
regenerate
replace
upload alternate
trim
split
extend
reorder
transition
mute
voice-over
caption
lock
render
```

---

# 40. New Material During Production

Your requirement that users can introduce new footage even late in production is important.

Implement:

```text
ADD MATERIAL
      ↓
upload
      ↓
analyze
      ↓
identify associated:
   people
   events
   dates
   locations
      ↓
suggest screenplay/timeline placement
```

Never automatically overwrite approved edits.

Show:

> "This video appears to show the 1983 graduation described in Chapter 5. Add it to Scene 5.3?"

---

# 41. AI Service Architecture

Create specialized AI services instead of one giant "agent."

```text
ai/

  interviewer/
  interview-director/
  transcript-analyzer/
  story-extractor/
  timeline-builder/
  media-analyzer/
  style-analyzer/
  screenplay-writer/
  shot-planner/
  continuity-agent/
  video-prompt-builder/
  clip-qc/
```

Each agent must have:

```text
input schema
output schema
system instructions
model configuration
test fixtures
evaluation cases
```

---

# 42. Model Router

Centralize model names.

```typescript
export const MODEL_ROLES = {

  realtimeInterview:
    process.env.GEMINI_LIVE_MODEL,

  reasoning:
    process.env.GEMINI_REASONING_MODEL,

  extraction:
    process.env.GEMINI_EXTRACTION_MODEL,

  screenplay:
    process.env.GEMINI_SCREENPLAY_MODEL,

  mediaAnalysis:
    process.env.GEMINI_MEDIA_MODEL,

  video:
    process.env.VEO_MODEL

};
```

Never scatter model IDs throughout application code.

This is particularly important because Gemini/Veo model versions change over time.

---

# 43. Main API Surface

## Projects

```http
POST   /api/projects
GET    /api/projects/:id
PATCH  /api/projects/:id
DELETE /api/projects/:id
```

## Media

```http
POST /api/projects/:id/media/upload-url

POST /api/media/:id/process

GET  /api/media/:id

DELETE /api/media/:id
```

---

# 44. Style Lab API

```http
POST /api/styles

POST /api/styles/:id/materials

POST /api/styles/:id/analyze

GET /api/styles/:id/profile

PATCH /api/styles/:id/profile
```

---

# 45. Interview API

```http
POST /api/projects/:id/interviews

POST /api/interviews/:id/messages

POST /api/interviews/:id/end

GET /api/interviews/:id/transcript

GET /api/interviews/:id/stories
```

WebSocket:

```text
/ws/interviews/:id/live
```

---

# 46. Screenplay API

```http
POST /api/projects/:id/screenplays

GET /api/screenplays/:id

POST /api/screenplays/:id/scenes

POST /api/scenes/:id/rewrite

POST /api/scenes/:id/split

POST /api/scenes/:id/approve

POST /api/scenes/:id/lock
```

---

# 47. Cinema API

```http
POST /api/scenes/:id/generate

GET /api/generations/:id

POST /api/shots/:id/regenerate

POST /api/shots/:id/approve

POST /api/projects/:id/render

GET /api/renders/:id
```

---

# 48. Event System

Use domain events.

Examples:

```text
media.uploaded

media.processed

interview.started

interview.completed

transcript.created

story.created

screenplay.created

scene.approved

shot.generation.requested

shot.generated

shot.approved

render.requested

render.completed
```

This simplifies workflows and future integrations.

---

# 49. Temporal Workflows

Create:

```text
ProcessMediaWorkflow

AnalyzeStyleMaterialWorkflow

FinalizeInterviewWorkflow

GenerateScreenplayWorkflow

GenerateSceneWorkflow

RenderFilmWorkflow
```

Example:

```python
@workflow.defn
class GenerateSceneWorkflow:

    @workflow.run
    async def run(self, scene_id):

        scene = await load_scene(scene_id)

        prompt = await build_prompt(scene)

        job = await generate_video(prompt)

        asset = await wait_for_video(job)

        qc = await evaluate_video(asset, scene)

        await save_result(asset, qc)
```

---

# 50. Repository Layout

Codex should create:

```text
ai-biographer/

  apps/

    web/
      app/
      components/
      hooks/
      lib/

    api/
      app/
        api/
        domain/
        services/
        ai/
        workflows/
        repositories/

  workers/

    media/
    rendering/

  packages/

    schemas/
    ui/
    config/

  infrastructure/

    docker/
    terraform/

  prompts/

    interviewer/
    interview-director/
    style-analyzer/
    screenplay/
    shot-planner/
    continuity/
    qc/

  tests/

    fixtures/
    integration/
    evals/

  docker-compose.yml

  README.md
```

---

# 51. Development Environment

`docker-compose.yml`:

```text
postgres
redis
minio
api
worker
web
```

MinIO emulates object storage locally.

Production:

```text
PostgreSQL → Cloud SQL

MinIO → Google Cloud Storage

local worker → Cloud Run / Kubernetes worker

Redis → Memorystore

Temporal → Temporal Cloud
```

---

# 52. Authentication

Use either:

```text
Auth.js
```

or

```text
Clerk
```

Required roles:

```text
OWNER

SUBJECT

EDITOR

VIEWER
```

A project may therefore involve:

```text
biography subject
family member
professional editor
producer
```

---

# 53. Privacy Architecture

This product will store unusually intimate information.

Privacy must be a first-class subsystem.

Required controls:

```text
explicit recording consent

media ownership declaration

project visibility

per-user authorization

encrypted object storage

encryption in transit

audit trail

export project

delete project

delete individual recording

delete AI-derived information

retention policy

model-provider disclosure
```

---

# 54. Sensitive Interview Design

The interviewer must recognize potentially sensitive subjects such as:

```text
death
trauma
medical experiences
family conflict
abuse
war
bereavement
```

Its goal is not therapy.

Use interviewer rules such as:

```text
Do not pressure the subject.

Do not repeatedly ask a declined question.

Allow subjects to skip a topic.

Do not diagnose.

Distinguish reported memories from independently established facts.
```

---

# 55. Copyright and Interviewer Style

Style Lab should learn **abstract techniques**, not impersonate living journalists.

Store characteristics such as:

```text
short open questions

gentle follow-ups

long periods before subject interruption

chronological callbacks
```

rather than:

```text
"pretend exactly to be Journalist X."
```

This also produces a more flexible product.

---

# 56. Observability

Implement OpenTelemetry.

Track:

```text
request latency

model latency

token usage

video generation cost

generation failure rate

transcoding duration

upload failures

interview disconnects

screenplay approval rate

scene regeneration rate
```

Every AI invocation gets:

```text
trace_id

project_id

agent_type

prompt_version

model

latency

cost estimate
```

Do not put private transcript content into general application logs.

---

# 57. Prompt Versioning

Prompts are source code.

Example:

```text
prompts/interviewer/v1.md

prompts/interviewer/v2.md
```

Database stores:

```text
prompt_version
model_version
generation_parameters
```

for reproducibility.

---

# 58. AI Evaluation Framework

Create regression examples such as:

```text
evals/

 interview/
   childhood-memory.json
   emotional-topic.json
   vague-answer.json

 screenplay/
   chronology.json
   visual-grounding.json

 continuity/
   recurring-character.json
   historical-period.json
```

Metrics:

```text
question quality

repetition

fact grounding

hallucination

story coherence

continuity

emotional appropriateness
```

---

# 59. Codex Master Implementation Instructions

Provide Codex with the following rules.

## Role

You are the lead engineer implementing **AI Biographer**, a production-quality multimodal biography application.

Use:

```text
Frontend:
Next.js
React
TypeScript
Tailwind
shadcn/ui

Backend:
Python 3.12
FastAPI
Pydantic
SQLAlchemy

Database:
PostgreSQL
pgvector

Jobs:
Temporal

Cache:
Redis

Object storage:
S3-compatible abstraction
MinIO locally
Google Cloud Storage in production

AI:
Google GenAI SDK
Gemini
Gemini Live
Veo

Media:
FFmpeg
ffprobe
```

---

# 60. Mandatory Engineering Rules for Codex

Codex must:

1. Use strict TypeScript.
2. Use Python type annotations.
3. Use Pydantic for API boundaries.
4. Create database migrations.
5. Separate domain logic from route handlers.
6. Never expose Gemini credentials to the browser.
7. Use ephemeral tokens where direct Live API browser access is enabled.
8. Use signed upload URLs.
9. Never put large media through ordinary API request bodies.
10. Store permanent media in application object storage.
11. Validate every AI structured response.
12. Maintain AI provider abstraction layers.
13. Keep model names in configuration.
14. Add unit tests for domain logic.
15. Add integration tests for APIs.
16. Add AI evaluation fixtures.
17. Implement retry/idempotency for asynchronous tasks.
18. Store provenance for generated facts.
19. Version screenplays.
20. Never overwrite approved content.

---

# 61. Codex Phase 1 — Foundation

Implement first:

```text
monorepo
authentication
projects
PostgreSQL
object storage
media uploads
media library
background processing
dashboard
```

Acceptance test:

```text
User can:

create biography
upload JPG
upload MP4
upload MP3
upload DOCX

and see each asset successfully processed.
```

---

# 62. Codex Phase 2 — Style Lab

Implement:

```text
Style Lab page

multiformat upload

audio extraction

transcript creation

speaker segmentation

question extraction

style analysis

editable Style Profile
```

Acceptance test:

Given an interview video, system produces:

```text
transcript

speaker turns

interviewer questions

question classifications

style profile

representative examples
```

---

# 63. Codex Phase 3 — Interview Studio

Implement:

```text
text interview

voice interview

Gemini Live integration

recording

live transcript

Interview Director

style selection

media upload during interview

session resume
```

Acceptance test:

A user can conduct a 15-minute voice conversation, interrupt the AI naturally, upload a photograph, finish the interview and retrieve the complete transcript. Gemini Live supports barge-in and audio transcription, making those appropriate requirements for the implementation. ([Google AI for Developers][3])

---

# 64. Codex Phase 4 — Biography Intelligence

Implement:

```text
people extraction

places extraction

event extraction

story segmentation

timeline construction

life chapters

evidence linking

unanswered-question detection
```

UI:

```text
Timeline

People

Places

Stories

Unresolved questions
```

---

# 65. Codex Phase 5 — Screenplay Editor

Implement:

```text
story selection

screenplay generation

scene editor

shot breakdown

source citations

media attachment

version history

approval workflow
```

Acceptance criterion:

Every generated scene contains evidence references or is explicitly marked:

```text
DRAMATIZED
```

---

# 66. Codex Phase 6 — Cinema Studio

Implement:

```text
Continuity Bible

Character Pack

Location Pack

shot generation

Veo adapter

generation queue

generated media viewer

approve/regenerate

timeline

FFmpeg assembly
```

For current Veo behavior, design shot jobs around roughly 8-second generated segments and support reference imagery/extension behind capability flags. ([Google AI for Developers][4])

---

# 67. Codex Phase 7 — Full Rendering

Pipeline:

```text
approved shots

+ uploaded footage

+ narration

+ dialogue

+ ambient audio

+ music

+ captions

       ↓

FFmpeg

       ↓

1080p MP4
```

Produce:

```text
final.mp4

captions.vtt

screenplay.pdf

transcript.docx

project_metadata.json
```

---

# 68. First Codex Task

The first prompt sent to Codex should be:

```text
Create the initial AI Biographer monorepo.

Implement:

1. apps/web as a Next.js TypeScript application.
2. apps/api as a Python FastAPI application.
3. PostgreSQL + pgvector.
4. Redis.
5. MinIO development object storage.
6. SQLAlchemy models and Alembic migrations.
7. Biography Project CRUD.
8. MediaAsset CRUD.
9. Signed multipart media uploads.
10. A media-processing worker using FFmpeg.
11. Docker Compose for the complete development stack.
12. Unit and integration tests.
13. .env.example.
14. README with setup instructions.

Create four top-level navigation items:

- Style Lab
- Interview Studio
- Screenplay Editor
- Cinema Studio

The dashboard must allow the user to create a Biography Project.

Inside a Biography Project, implement a Media Library with drag-and-drop uploads.

Supported initial formats:

Images:
jpg, jpeg, png, webp, heic

Video:
mp4, mov, mpeg, mpg, m4v, webm

Audio:
mp3, wav, m4a, aac

Documents:
txt, md, docx, pdf

On media upload:

1. validate MIME type;
2. store the original file;
3. calculate SHA-256 checksum;
4. create MediaAsset record;
5. enqueue ProcessMediaWorkflow;
6. run ffprobe when applicable;
7. extract metadata;
8. generate thumbnail/proxy where applicable;
9. update processing status.

Architect all cloud dependencies behind interfaces.

Do not implement fake Gemini functionality.

Create AI provider interfaces but leave Google-specific implementation for the next development phase.

Use production-quality error handling and tests.
```

---

# 69. Second Codex Task — Google AI Layer

After the foundation works:

```text
Implement the Google AI provider package for AI Biographer.

Use the Google GenAI SDK.

Create:

GeminiTextProvider

GeminiMediaUnderstandingProvider

GeminiLiveProvider

VeoVideoProvider

Implement environment-configurable model IDs.

Add Gemini file staging:

application object storage
    ↓
temporary Gemini Files upload
    ↓
model request
    ↓
store output
    ↓
delete temporary Gemini file when practical

Gemini Files must NOT be treated as permanent application storage.

Implement structured JSON generation with Pydantic validation and retry when semantic validation fails.

Add tracing for every invocation.

Never log raw personal interview data.
```

Structured output should use Gemini's supported JSON-schema mechanism rather than parsing loosely formatted prose. ([Google AI for Developers][5])

---

# 70. Third Codex Task — Style Lab

```text
Implement Style Lab.

The page shall allow users to:

create Style Profiles;

upload interviews;

view uploaded media;

launch analysis;

review transcript;

identify interviewer/interviewee turns;

see interviewer questions;

see extracted interview techniques;

edit resulting Style Profile;

activate profile for interviews.

Use the StyleProfile domain schema.

Do not generate a style solely from keyword statistics.

Use Gemini to classify interviewer behavior and return schema-valid structured results.

Store embeddings for representative examples.

Create tests using supplied text interview fixtures.
```

---

# 71. Fourth Codex Task — Interview Studio

```text
Implement Interview Studio.

Support:

text conversation;

voice conversation;

Gemini Live;

recording;

transcription;

barge-in;

resume session;

selected Style Profile;

Interview Director state machine;

media upload during conversation;

automatic story detection;

session ending and summarization.

The Interview Director is separate from the user-facing Interviewer.

The Director returns structured state decisions.

The Interviewer produces conversational responses.

Persist every turn.

Persist timestamps.

Persist recording metadata.

After the session invoke FinalizeInterviewWorkflow.
```

---

# 72. Fifth Codex Task — Screenplay

```text
Implement Screenplay Editor.

Input:

selected story
life events
transcript evidence
media assets
continuity bible

Output:

screenplay
scenes
shots

Use structured generation.

Each scene must contain:

narrative purpose
duration
narration
dialogue
characters
location
period
emotion
visual description
supporting assets
evidence
shot plan

Expose source evidence from every screenplay scene.

Support rewrite, split, merge, approve and lock.

Maintain complete version history.
```

---

# 73. Sixth Codex Task — Cinema Studio

```text
Implement Cinema Studio.

Create a nonlinear timeline editor supporting:

video
voiceover
dialogue
music
ambient audio
captions.

Implement Veo generation through the provider interface.

Each Shot generation must combine:

shot specification
continuity bible
character pack
location pack
period pack
reference imagery

Track:

prompt
model
seed/config when available
input assets
output asset
generation status
quality evaluation

Allow:

generate
regenerate
replace
approve
lock

Implement FFmpeg timeline rendering.
```

---

# 74. MVP Definition

A genuine MVP is complete when one person can:

```text
1. Create a biography.

2. Upload several photos.

3. Upload a sample interviewer video.

4. Create a Style Profile.

5. Conduct a voice interview.

6. Receive recording + transcript.

7. See stories extracted from the interview.

8. Pick one story.

9. Produce an editable screenplay.

10. Approve the screenplay.

11. Generate several video shots.

12. Combine generated shots and uploaded photos/video.

13. Add narration.

14. Render a 2–5 minute biographical film.
```

Do **not** initially attempt a complete 60–90 minute feature film.

Solve the 2–5 minute story extremely well first.

---

# 75. Longer-Term Architecture

Once the MVP is stable:

```text
Biography Project

       ↓

100+ interviews

       ↓

thousands of media assets

       ↓

dozens of life chapters

       ↓

multiple editors

       ↓

multiple film versions

       ↓

full-length documentary
```

At that point introduce additional services where justified:

```text
dedicated search index

graph database

GPU render cluster

media CDN

collaborative editing

multilingual dubbing

professional color pipeline

digital asset management
```

---

# 76. Most Important Product Differentiator

The application's moat should **not** simply be:

> "We use Gemini and Veo."

Those capabilities will be available to many products.

The defensible system is:

```text
Interview intelligence
        +
Biography knowledge graph
        +
Evidence/provenance
        +
Editorial workflow
        +
Continuity Bible
        +
Human approvals
        +
Media-to-story associations
        +
Cinematic continuity
```

Together they transform a collection of AI APIs into a genuine **AI biographer and documentary production system**.

---

# 77. Recommended Initial End-to-End Flow

```text
                 AI BIOGRAPHER

                      │
                      ▼
                Create Project
                      │
          ┌───────────┴────────────┐
          │                        │
          ▼                        ▼
      STYLE LAB               MEDIA LIBRARY
          │                        │
          │                  Photos / Videos
          │                  Audio / Documents
          ▼                        │
   Interview Style                 │
          │                        │
          └──────────┬─────────────┘
                     ▼
              INTERVIEW STUDIO
                     │
            Voice + Text + Media
                     │
                     ▼
                Transcript
                     │
                     ▼
             Biography Engine
                     │
       ┌─────────────┼──────────────┐
       ▼             ▼              ▼
    People        Timeline        Stories
                                     │
                                     ▼
                           SCREENPLAY EDITOR
                                     │
                                Chapters
                                     │
                                  Scenes
                                     │
                                   Shots
                                     │
                                     ▼
                              Human Approval
                                     │
                                     ▼
                              CINEMA STUDIO
                                     │
                  ┌──────────────────┼────────────┐
                  ▼                  ▼            ▼
              User Media           Veo        Narration
                  │                  │            │
                  └──────────────────┼────────────┘
                                     ▼
                               Timeline Edit
                                     │
                                     ▼
                                Final Render
                                     │
                                     ▼
                           BIOGRAPHICAL FILM
```

This architecture gives Codex clearly bounded components to implement while preserving a path from the first MVP to a serious documentary-production platform.

A few architectural decisions in the specification are worth emphasizing. **First**, I would make the Biography Engine—events, people, places, evidence, relationships and stories—the center of the system rather than making the transcript the center. That lets ten or fifty later interviews enrich the same biography instead of producing disconnected chat histories.

**Second**, the separation between an invisible **Interview Director** and the speaking **Interviewer** is particularly important. It gives you a way to reason about coverage, follow-up questions, chronology, emotional sensitivity and missing evidence without making the visible conversation robotic.

**Third**, I would make the **Continuity Bible** a formal data object from day one. Veo 3.1 can use reference images, first/last-frame guidance and video extension, but maintaining a person across a 40-scene biography still requires application-level state and explicit continuity constraints; the video model alone should not be expected to remember the film. ([Google AI for Developers][4])

Finally, the **Style Lab should begin with retrieval + structured style extraction rather than model fine-tuning**. That gives you traceability, lets an editor combine multiple interviewer styles, and makes adding or deleting source interviews straightforward. Gemini's structured-output capabilities are well suited to converting interview examples into stable schemas for techniques, pacing, tone, question types and follow-up behavior. ([Google AI for Developers][5])

The natural next implementation artifact would be the **actual starter repository specification down to database SQLAlchemy models, Pydantic schemas, REST contracts, folder-by-folder code skeleton, Docker Compose, and the first 10–15 Codex implementation prompts**, so Codex can build the MVP sequentially rather than trying to create the whole platform in one pass.

[1]: https://ai.google.dev/gemini-api/docs/files?utm_source=chatgpt.com "Files API  |  Gemini API  |  Google AI for Developers"
[2]: https://ai.google.dev/gemini-api/docs/get-started?utm_source=chatgpt.com "Getting started  |  Gemini API  |  Google AI for Developers"
[3]: https://ai.google.dev/gemini-api/docs/live-api?utm_source=chatgpt.com "Gemini Live API overview  |  Gemini API  |  Google AI for Developers"
[4]: https://ai.google.dev/gemini-api/docs/veo?hl=en&utm_source=chatgpt.com "Generate videos with Veo 3.1 in Gemini API  |  Google AI for Developers"
[5]: https://ai.google.dev/gemini-api/docs/structured-output?authuser=14&hl=en&utm_source=chatgpt.com "Structured outputs  |  Gemini API  |  Google AI for Developers"
