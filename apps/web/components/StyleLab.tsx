"use client";
import { useSession } from "next-auth/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import Link from "next/link";
import {
  Sparkles,
  Mic,
  FileText,
  Check,
  Plus,
  ArrowRight,
  BookOpen,
  Play,
  LockKeyhole,
} from "lucide-react";
import { request, type Project, type MediaAsset } from "../lib/api";
import { Button } from "./ui/button";
import MediaLibrary from "./MediaLibrary";

type Profile = {
  id: string;
  name: string;
  project_id: string;
  description: string;
};
export type Source = {
  id: string;
  asset_id: string;
  filename: string;
  mime_type: string;
  duration_ms: number;
  reviewed: boolean;
  revision: number;
  turn_count: number;
};
export type Turn = {
  id: string;
  source_id: string;
  speaker: string;
  role: "unknown" | "interviewer" | "participant" | "other";
  role_override?: boolean;
  start_ms: number;
  end_ms: number;
  text: string;
  filename?: string;
  asset_id?: string;
};
type Pattern = {
  id: string;
  category: string;
  instruction: string;
  example: string;
  confidence: number;
  evidence_ids: string[];
  review_status: string;
  origin: string;
};
type Job = {
  id: string;
  source_id: string | null;
  kind: string;
  state: string;
  completed: number;
  total: number;
  error: string | null;
};
type Version = {
  id: string;
  number: number;
  created_at: string;
  pattern_count: number;
};
export type Detail = Profile & {
  sources: Source[];
  patterns: Pattern[];
  jobs: Job[];
  versions: Version[];
  provider_ready: boolean;
};
type Snapshot = {
  number: number;
  snapshot: { patterns: (Pattern & { evidence: Turn[] })[] };
};
type Action = (work: () => Promise<unknown>, message?: string) => Promise<void>;
const active = (j: Job) =>
  ["pending", "dispatched", "running", "stopping"].includes(j.state);
const time = (ms: number) =>
  `${Math.floor(ms / 60000)}:${Math.floor((ms / 1000) % 60)
    .toString()
    .padStart(2, "0")}`;
const json = (method: string, body: unknown) => ({
  method,
  body: JSON.stringify(body),
});

export default function StyleLab() {
  const cache = useQueryClient();
  const { data: session } = useSession();
  const [selected, setSelected] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const profiles = useQuery({
    queryKey: ["style-profiles", session?.user?.email],
    queryFn: () => request<Profile[]>("/profiles"),
  });
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => request<Project[]>("/projects"),
  });
  const profileId = selected || profiles.data?.[0]?.id || "";
  const detail = useQuery({
    queryKey: ["style", profileId],
    queryFn: () => request<Detail>(`/profiles/${profileId}`),
    enabled: !!profileId,
    refetchInterval: 4000,
  });
  const action: Action = async (work, message = "Saved") => {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      await work();
      await cache.invalidateQueries({ queryKey: ["style"] });
      await cache.invalidateQueries({ queryKey: ["style-turns"] });
      await cache.invalidateQueries({ queryKey: ["style-profiles"] });
      await cache.invalidateQueries({ queryKey: ["media"] });
      setNotice(message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Please try again");
    } finally {
      setBusy(false);
    }
  };
  const create = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    void action(async () => {
      const p = await request<Detail>(
        "/profiles",
        json("POST", Object.fromEntries(data)),
      );
      setSelected(p.id);
      setCreating(false);
    }, "Interviewer profile created");
  };
  return (
    <div className="style-lab">
      <div className="page-heading">
        <div>
          <div className="eyebrow">01 / THE ART OF LISTENING</div>
          <h1>Style Lab</h1>
          <p className="subtitle">
            Shape an interviewer who asks with care, and listens like you.
          </p>
        </div>
        <Button onClick={() => setCreating(!creating)}>
          <Plus size={16} /> New profile
        </Button>
      </div>
      <div className="style-intro">
        <div className="style-intro-icon">
          <Sparkles size={29} />
        </div>
        <div>
          <h2>Learn the approach. Preserve the human touch.</h2>
          <p>
            Recordings teach your interviewer how to listen, probe, and follow a
            story. You review the evidence and decide what becomes part of its
            style.
          </p>
        </div>
        <span className="status-pill">
          <LockKeyhole size={12} /> Private to you
        </span>
      </div>
      {(creating || profiles.data?.length === 0) && (
        <form className="style-panel" onSubmit={create}>
          <h2>Create an interviewer profile</h2>
          <div className="style-form-grid">
            <label>
              Profile name
              <input
                name="name"
                required
                maxLength={200}
                placeholder="A thoughtful life-story interviewer"
              />
            </label>
            <label>
              Biography workspace
              <select name="project_id" required defaultValue="">
                <option value="" disabled>
                  Select a biography
                </option>
                {projects.data
                  ?.filter((p) => p.role === "OWNER")
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title || p.subject_name}
                    </option>
                  ))}
              </select>
            </label>
          </div>
          <label>
            What should this interviewer feel like?
            <textarea
              name="description"
              maxLength={3000}
              placeholder="A short note about the approach you want to develop."
            />
          </label>
          <Button
            disabled={busy || !projects.data?.some((p) => p.role === "OWNER")}
          >
            Create profile
          </Button>
          {!projects.data?.some((p) => p.role === "OWNER") && (
            <p className="style-help">
              <Link href="/">Create a biography first</Link> to hold your source
              recordings.
            </p>
          )}
        </form>
      )}
      {(error || profiles.error || detail.error || projects.error) && (
        <div role="alert" className="error">
          {error ||
            profiles.error?.message ||
            detail.error?.message ||
            projects.error?.message}
        </div>
      )}
      {notice && (
        <div role="status" className="success">
          {notice}
        </div>
      )}
      {profiles.isPending && (
        <p className="style-help">Loading your interviewer profiles…</p>
      )}
      {!!profiles.data?.length && (
        <div className="style-profile-picker">
          <label>
            Interviewer profile
            <select
              value={profileId}
              onChange={(e) => {
                setSelected(e.target.value);
                setNotice("");
                setError("");
              }}
            >
              {profiles.data.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <span>
            {detail.data?.versions.length
              ? `Latest: version ${detail.data.versions[0].number}`
              : "Unpublished draft"}
          </span>
        </div>
      )}
      {detail.data && (
        <Workspace
          key={profileId}
          profile={detail.data}
          action={action}
          busy={busy}
        />
      )}
    </div>
  );
}

function Workspace({
  profile: p,
  action,
  busy,
}: {
  profile: Detail;
  action: Action;
  busy: boolean;
}) {
  const [tab, setTab] = useState("recordings");
  const [sourceId, setSourceId] = useState("");
  const [consent, setConsent] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [selectedTurns, setSelectedTurns] = useState<Turn[]>([]);
  const [version, setVersion] = useState<Snapshot | null>(null);
  const media = useQuery({
    queryKey: ["media", p.project_id],
    queryFn: () => request<MediaAsset[]>(`/projects/${p.project_id}/media`),
    refetchInterval: 5000,
  });
  const source = p.sources.find((s) => s.id === sourceId) || p.sources[0];
  const blocked = busy || p.jobs.some(active);
  const base = `/profiles/${p.id}`;
  const approved = p.patterns.filter(
    (x) => x.review_status === "approved",
  ).length;
  const deleteRecording = (
    filename: string,
    assetId: string,
    sourceId?: string,
  ) => {
    if (
      !window.confirm(
        `Delete ${filename}? This permanently removes the original recording, previews, its transcript, and dependent draft patterns. Published evidence and recordings used by other profiles are protected.`,
      )
    )
      return;
    void action(async () => {
      await request(
        sourceId
          ? `${base}/sources/${sourceId}`
          : `/projects/${p.project_id}/media/${assetId}`,
        { method: "DELETE" },
      );
      setSelectedTurns([]);
      if (sourceId) setSourceId("");
    }, "Recording deleted");
  };
  const openTranscript = (id: string) => {
    window.location.assign(`/style-lab/${p.id}/scripts/${id}`);
  };
  const startTranscript = (sourceId: string) =>
    action(
      () =>
        request(
          `${base}/sources/${sourceId}/transcribe`,
          json("POST", {
            request_id: crypto.randomUUID(),
            provider_consent: true,
          }),
        ),
      "Transcription started. Follow its progress here, then choose Open transcript.",
    );
  const startUploaded = (assetId: string) =>
    action(async () => {
      const attached = await request<{ id: string }>(
        `${base}/assets`,
        json("POST", { asset_id: assetId }),
      );
      await request(
        `${base}/sources/${attached.id}/transcribe`,
        json("POST", {
          request_id: crypto.randomUUID(),
          provider_consent: true,
        }),
      );
    }, "Recording added and transcription started. Progress appears below.");
  const transcriptionDisabled = blocked || !p.provider_ready || !consent;
  const tabs = [
    {
      id: "recordings",
      label: "Recordings",
      icon: Mic,
      count: p.sources.length,
    },
    {
      id: "transcript",
      label: "Transcript evidence",
      icon: FileText,
      count: p.sources.filter((s) => s.turn_count > 0).length,
    },
    {
      id: "patterns",
      label: "Style & examples",
      icon: Sparkles,
      count: p.patterns.length,
    },
    {
      id: "publish",
      label: "Publish",
      icon: BookOpen,
      count: p.versions.length,
    },
  ];
  return (
    <>
      <nav className="style-tabs" aria-label="Style Lab steps">
        {tabs.map(({ id, label, icon: Icon, count }, i) => (
          <button
            key={id}
            type="button"
            aria-current={tab === id ? "step" : undefined}
            className={tab === id ? "selected" : ""}
            onClick={() => setTab(id)}
          >
            <Icon size={16} />
            <span>
              {i + 1}. {label}
            </span>
            <small>{count}</small>
          </button>
        ))}
      </nav>
      <div className="style-layout">
        <section className="style-main">
          {(tab === "recordings" || tab === "transcript") && (
            <div className="style-processing-setup">
              <h3>Turn recordings into a transcript</h3>
              <p>
                1. Upload a recording. 2. Choose Create transcript. 3. Open the
                finished transcript to review its words and speakers.
              </p>
              {!p.provider_ready && (
                <p role="status" className="error">
                  Transcription setup required: configure GEMINI_API_KEY and
                  GEMINI_MODEL on the server, then restart the API and worker.
                  Your uploads are saved; automatic transcription is unavailable
                  until setup is complete.
                </p>
              )}
              <label className="style-checkbox">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />{" "}
                I authorize sending these recordings and reviewed transcripts to
                Gemini for this profile.
              </label>
              {p.provider_ready && !consent && (
                <p className="style-help">
                  Check the authorization box to enable Create transcript.
                </p>
              )}
            </div>
          )}
          {p.jobs
            .filter(
              (j) =>
                active(j) ||
                ["failed", "cancelled"].includes(j.state) ||
                j.state === "completed",
            )
            .map((j) => {
              const recording = p.sources.find((s) => s.id === j.source_id);
              const complete = j.state === "completed";
              const percent = complete
                ? 100
                : j.total
                  ? Math.floor((j.completed / j.total) * 100)
                  : null;
              return (
                <div
                  className="style-job"
                  key={j.id}
                  aria-label={`Processing ${recording?.filename || "interview style"}`}
                >
                  <strong>
                    {j.kind === "transcribe"
                      ? complete
                        ? "Transcript ready"
                        : "Creating transcript"
                      : "Comparing interview style"}
                    {recording ? ` · ${recording.filename}` : ""}
                  </strong>
                  <span role="status">
                    {j.state === "stopping"
                      ? "Stopping — waiting for the worker to close the request"
                      : j.state === "cancelled"
                        ? "Stopped — saved sections retained"
                        : complete
                          ? "Processing complete · 100%"
                          : j.state === "failed"
                            ? "Processing interrupted"
                            : j.state === "pending" || j.state === "dispatched"
                              ? "Queued — waiting for the worker"
                              : percent === null
                                ? "Preparing audio…"
                                : `${j.kind === "transcribe" ? "Transcribing" : "Analyzing style"} · ${percent}%`}
                    {j.total > 0 &&
                      ` · ${j.completed} of ${j.total} sections saved`}
                  </span>
                  <progress
                    value={percent === null ? undefined : percent}
                    max={100}
                    aria-label="Processing progress"
                  />
                  {active(j) && (
                    <p className="style-help">
                      Progress updates after each section is saved. You can
                      leave this page and return later.
                    </p>
                  )}
                  {j.error && <p className="error">{j.error}</p>}
                  {["failed", "cancelled"].includes(j.state) && (
                    <Button
                      variant="outline"
                      disabled={blocked}
                      onClick={() =>
                        void action(
                          () =>
                            request(`/jobs/${j.id}/retry`, { method: "POST" }),
                          "Processing resumed from saved progress",
                        )
                      }
                    >
                      Resume processing
                    </Button>
                  )}
                  {["failed", "cancelled", "completed"].includes(j.state) && (
                    <Button
                      variant="destructive"
                      disabled={blocked}
                      onClick={() => {
                        const transcript = j.kind === "transcribe";
                        if (
                          !window.confirm(
                            transcript
                              ? `Delete processing and script for "${recording?.filename || "this recording"}"? This removes the working transcript, approved script versions, searchable memory, related patterns and published style versions, and profile analysis history. The uploaded recording is kept. Exported files in your local folders are not deleted. This cannot be undone.`
                              : "Delete this processing record and its saved checkpoint? Existing scripts and style patterns are kept.",
                          )
                        )
                          return;
                        void action(
                          async () => {
                            await request(`/jobs/${j.id}`, {
                              method: "DELETE",
                            });
                            setSelectedTurns([]);
                            setVersion(null);
                          },
                          transcript
                            ? "Processing and script deleted; recording retained"
                            : "Processing record deleted",
                        );
                      }}
                    >
                      {j.kind === "transcribe"
                        ? "Delete processing & script"
                        : "Delete processing record"}
                    </Button>
                  )}
                  {active(j) && (
                    <Button
                      variant="destructive"
                      disabled={busy || j.state === "stopping"}
                      onClick={() =>
                        void action(
                          () =>
                            request(`/jobs/${j.id}/stop`, { method: "POST" }),
                          "Stop requested. Saved sections are retained; a request already accepted by Gemini may still finish on Google's side.",
                        )
                      }
                    >
                      {j.state === "stopping" ? "Stopping…" : "Stop processing"}
                    </Button>
                  )}
                  {(complete || j.state === "cancelled") && recording && (
                    <>
                      <p className="style-help">
                        {recording.turn_count
                          ? `${recording.turn_count} transcript turns are ready for review.`
                          : j.state === "cancelled"
                            ? "No transcript sections were saved before stopping. Resume processing when ready."
                            : "No speech was returned. Open the transcript to review the recording and add missing turns manually."}
                      </p>
                      <Button onClick={() => openTranscript(recording.id)}>
                        Open transcript <ArrowRight size={14} />
                      </Button>
                    </>
                  )}
                </div>
              );
            })}
          {tab === "recordings" && (
            <>
              <div className="style-section-heading">
                <div>
                  <h2>Your source recordings</h2>
                  <p>
                    Choose interviews that capture the approach you want to
                    learn.
                  </p>
                </div>
                <Button
                  variant="outline"
                  onClick={() => setShowUpload(!showUpload)}
                >
                  <Plus size={15} /> Upload recordings
                </Button>
              </div>
              {showUpload && (
                <div className="style-panel">
                  <MediaLibrary projectId={p.project_id} />
                  <p className="style-help">
                    Once file preparation finishes, choose Create transcript
                    below. Uploading and preparing the file do not start AI
                    transcription.
                  </p>
                </div>
              )}
              <form
                className="style-attach"
                onSubmit={(e) => {
                  e.preventDefault();
                  const id = new FormData(e.currentTarget).get("asset");
                  void action(
                    () =>
                      request(`${base}/assets`, json("POST", { asset_id: id })),
                    "Recording added to this profile",
                  );
                }}
              >
                <label>
                  Available recordings
                  <select name="asset" required defaultValue="">
                    <option value="" disabled>
                      Choose a processed recording
                    </option>
                    {media.data
                      ?.filter(
                        (a) =>
                          a.status === "ready" &&
                          /^(audio|video)\//.test(a.mime_type) &&
                          !p.sources.some((s) => s.asset_id === a.id),
                      )
                      .map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.original_filename}
                        </option>
                      ))}
                  </select>
                </label>
                <Button disabled={blocked}>Add recording</Button>
              </form>
              {media.error && <p className="error">{media.error.message}</p>}
              {!p.sources.length && (
                <div className="empty-state">
                  <Mic size={30} />
                  <h3>A good interview is the starting point</h3>
                  <p>
                    Upload audio or video, then choose Create transcript. Long
                    recordings are processed in short sections with saved
                    progress.
                  </p>
                </div>
              )}
              {media.data
                ?.filter(
                  (a) =>
                    /^(audio|video)\//.test(a.mime_type) &&
                    !p.sources.some((s) => s.asset_id === a.id),
                )
                .map((a) => (
                  <article
                    className="style-source style-recording-action"
                    key={a.id}
                  >
                    <div>
                      <h3>{a.original_filename}</h3>
                      <p>
                        {a.status === "ready"
                          ? "File preparation complete · Transcript not started"
                          : a.status === "failed"
                            ? "File preparation failed. Retry from the upload library."
                            : a.status === "uploading"
                              ? "Upload incomplete — resume from the upload library"
                              : "Preparing uploaded file…"}
                      </p>
                      {["uploaded", "processing"].includes(a.status) && (
                        <progress
                          aria-label={`Preparing ${a.original_filename}`}
                        />
                      )}
                    </div>
                    <Button
                      disabled={transcriptionDisabled || a.status !== "ready"}
                      onClick={() => void startUploaded(a.id)}
                    >
                      Create transcript
                    </Button>
                    <Button
                      variant="destructive"
                      disabled={
                        blocked || ["uploaded", "processing"].includes(a.status)
                      }
                      onClick={() => deleteRecording(a.original_filename, a.id)}
                    >
                      Delete recording
                    </Button>
                  </article>
                ))}
              {p.sources.map((s) => {
                const job = p.jobs.find(
                  (j) => j.source_id === s.id && j.kind === "transcribe",
                );
                return (
                  <article
                    className="style-source style-recording-action"
                    key={s.id}
                  >
                    <div className="style-source-icon">
                      <Mic size={22} />
                    </div>
                    <div>
                      <h3>{s.filename}</h3>
                      <p>
                        {time(s.duration_ms)} · {s.turn_count} transcript turns
                        ·{" "}
                        {s.reviewed
                          ? "Reviewed"
                          : job?.state === "cancelled"
                            ? "Transcription stopped — resume to finish"
                            : job?.state === "stopping"
                              ? "Stopping transcription"
                              : job && active(job)
                                ? "Transcription in progress"
                                : s.turn_count
                                  ? "Ready for transcript review"
                                  : "Transcript not started"}
                      </p>
                    </div>
                    {!s.turn_count && !job && (
                      <Button
                        disabled={transcriptionDisabled}
                        onClick={() => void startTranscript(s.id)}
                      >
                        Create transcript
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      onClick={() => openTranscript(s.id)}
                    >
                      {s.turn_count || job?.state === "completed"
                        ? "Open transcript"
                        : "Transcript workspace"}{" "}
                      <ArrowRight size={14} />
                    </Button>
                    <Button
                      variant="destructive"
                      disabled={blocked}
                      onClick={() =>
                        deleteRecording(s.filename, s.asset_id, s.id)
                      }
                    >
                      Delete recording
                    </Button>
                  </article>
                );
              })}
            </>
          )}
          {tab === "transcript" && (
            <>
              <div className="style-section-heading">
                <div>
                  <h2>Listen, identify, refine</h2>
                  <p>
                    Confirm the interviewer and correct the words before
                    extracting style.
                  </p>
                </div>
              </div>
              {!source ? (
                <div className="empty-state">
                  <p>Add a recording first.</p>
                </div>
              ) : (
                <>
                  <label>
                    Recording
                    <select
                      value={source.id}
                      onChange={(e) => {
                        setSourceId(e.target.value);
                        setSelectedTurns([]);
                      }}
                    >
                      {p.sources.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.filename}
                        </option>
                      ))}
                    </select>
                  </label>
                  <RecordingPlayer
                    key={`${source.id}-${source.turn_count === 0 ? "empty" : "populated"}`}
                    projectId={p.project_id}
                    assetId={source.asset_id}
                    mime={source.mime_type}
                    action={action}
                  />
                  <div className="style-transcript-toolbar">
                    <span className="status-pill">
                      {source.reviewed
                        ? "Transcript approved"
                        : source.turn_count
                          ? "Review required"
                          : "No transcript yet"}
                    </span>
                    {!source.turn_count &&
                      !p.jobs.some(
                        (j) =>
                          j.source_id === source.id && j.kind === "transcribe",
                      ) && (
                        <Button
                          disabled={blocked || !p.provider_ready || !consent}
                          onClick={() =>
                            void action(
                              () =>
                                request(
                                  `${base}/sources/${source.id}/transcribe`,
                                  json("POST", {
                                    request_id: crypto.randomUUID(),
                                    provider_consent: true,
                                  }),
                                ),
                              "Transcription queued",
                            )
                          }
                        >
                          Create transcript
                        </Button>
                      )}
                    <Button
                      variant="outline"
                      onClick={() => openTranscript(source.id)}
                    >
                      Review & save script
                    </Button>
                  </div>
                  <p className="style-help">
                    Speaker labels are local to each audio section. Verify roles
                    throughout the recording; a label in one section does not
                    establish identity in another. Select exchanges to use as
                    pattern evidence.
                  </p>
                  <Transcript
                    key={`${source.id}-${source.turn_count === 0 ? "empty" : "populated"}`}
                    base={base}
                    source={source}
                    action={action}
                    blocked={blocked}
                    selected={selectedTurns}
                    setSelected={setSelectedTurns}
                  />
                  {!!selectedTurns.length && (
                    <div className="style-selection">
                      <span>{selectedTurns.length} turns selected</span>
                      <Button
                        disabled={!source.reviewed || blocked}
                        onClick={() => setTab("patterns")}
                      >
                        Create pattern from selection <ArrowRight size={14} />
                      </Button>
                    </div>
                  )}
                </>
              )}
            </>
          )}
          {tab === "patterns" && (
            <>
              <div className="style-section-heading">
                <div>
                  <h2>The shape of your conversations</h2>
                  <p>Review each observation against the original exchange.</p>
                </div>
                <Button
                  disabled={
                    blocked ||
                    !consent ||
                    !p.provider_ready ||
                    !p.sources.length ||
                    p.sources.some((s) => !s.reviewed)
                  }
                  onClick={() =>
                    void action(
                      () =>
                        request(
                          `${base}/analyze`,
                          json("POST", {
                            request_id: crypto.randomUUID(),
                            provider_consent: true,
                          }),
                        ),
                      "Style analysis queued; suggestions will need your review",
                    )
                  }
                >
                  <Sparkles size={15} /> Extract style
                </Button>
              </div>
              {!p.patterns.length && !selectedTurns.length && (
                <div className="empty-state">
                  <Sparkles size={30} />
                  <h3>Observable habits, supported by evidence</h3>
                  <p>
                    Approve your transcripts, then extract patterns. You can
                    also select transcript turns and write your own
                    evidence-backed rule.
                  </p>
                  <Button
                    variant="outline"
                    onClick={() => setTab("transcript")}
                  >
                    Review transcripts
                  </Button>
                </div>
              )}
              {!!selectedTurns.length && (
                <div className="style-panel">
                  <h3>
                    New pattern from {selectedTurns.length} selected turns
                  </h3>
                  <PatternEditor
                    base={base}
                    evidenceTurns={selectedTurns}
                    action={action}
                    blocked={blocked}
                    onSaved={() => setSelectedTurns([])}
                  />
                </div>
              )}
              {p.patterns.map((pattern) => (
                <PatternCard
                  key={pattern.id}
                  pattern={pattern}
                  base={base}
                  action={action}
                  blocked={blocked}
                />
              ))}
            </>
          )}
          {tab === "publish" && (
            <>
              <div className="style-section-heading">
                <div>
                  <h2>A style you can stand behind</h2>
                  <p>
                    Publishing freezes approved rules, examples, and their
                    supporting evidence.
                  </p>
                </div>
              </div>
              <div className="style-panel">
                <div className="style-publish-count">
                  {approved}
                  <span>approved patterns ready to publish</span>
                </div>
                <p className="style-help">
                  Pending and rejected patterns are excluded. Later draft edits
                  leave existing versions intact. This publishes a private style
                  version; the interview configuration will follow once the
                  reference-question plan is reviewed.
                </p>
                <Button
                  disabled={blocked || !approved}
                  onClick={() =>
                    void action(
                      () =>
                        request(
                          `${base}/versions`,
                          json("POST", { request_id: crypto.randomUUID() }),
                        ),
                      "Style version published",
                    )
                  }
                >
                  Publish style version
                </Button>
              </div>
              {p.versions.map((v) => (
                <div className="style-source" key={v.id}>
                  <Check size={21} />
                  <div>
                    <h3>Version {v.number}</h3>
                    <p>
                      {v.pattern_count} approved patterns ·{" "}
                      {new Date(v.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    onClick={() =>
                      void action(
                        async () =>
                          setVersion(
                            await request<Snapshot>(`${base}/versions/${v.id}`),
                          ),
                        "Published version opened",
                      )
                    }
                  >
                    View snapshot
                  </Button>
                </div>
              ))}
              {version && (
                <div className="style-panel">
                  <h3>Published version {version.number}</h3>
                  {version.snapshot.patterns.map((pat) => (
                    <article className="style-snapshot" key={pat.id}>
                      <span className="tiny-label">{pat.category}</span>
                      <h3>{pat.instruction}</h3>
                      <blockquote>{pat.example}</blockquote>
                      <details>
                        <summary>
                          Frozen evidence · {pat.evidence.length} turns
                        </summary>
                        {pat.evidence.map((t) => (
                          <p key={t.id}>
                            <strong>
                              {t.filename} · {time(t.start_ms)} · {t.role}
                            </strong>
                            <br />
                            {t.text}
                          </p>
                        ))}
                      </details>
                    </article>
                  ))}
                </div>
              )}
            </>
          )}
        </section>
        <aside className="style-aside">
          <div className="style-panel">
            <span className="tiny-label">YOUR REVIEW CHECKLIST</span>
            <h3>From recording to style</h3>
            <ul className="style-checklist">
              <li className={p.sources.length ? "done" : ""}>
                <Check size={15} /> Add source recordings
              </li>
              <li
                className={
                  p.sources.length && p.sources.every((s) => s.reviewed)
                    ? "done"
                    : ""
                }
              >
                <Check size={15} /> Verify words and speaker roles
              </li>
              <li className={approved ? "done" : ""}>
                <Check size={15} /> Approve supported patterns
              </li>
              <li className={p.versions.length ? "done" : ""}>
                <Check size={15} /> Publish a frozen version
              </li>
            </ul>
          </div>
          <div className="style-panel style-question-note">
            <BookOpen size={23} />
            <h3>What should we cover?</h3>
            <p>
              Your reference questions will supply the interview plan. The list
              is still pending.
            </p>
            <span className="status-pill">Awaiting reference questions</span>
            <p>
              Practice interviews and coverage reports follow the reviewed
              question plan.
            </p>
          </div>
          <div className="style-panel">
            <h3>AI processing</h3>
            <p>
              {p.provider_ready
                ? "Gemini is configured. Start transcription or analysis when you are ready."
                : "Automatic transcription and extraction need GEMINI_API_KEY and GEMINI_MODEL configured on the server. Manual transcript review and pattern creation are available now."}
            </p>
            {tab === "patterns" && (
              <label className="style-checkbox">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />{" "}
                I authorize sending reviewed transcripts to Gemini for style
                analysis.
              </label>
            )}
          </div>
        </aside>
      </div>
    </>
  );
}

export function RecordingPlayer({
  projectId,
  assetId,
  mime,
  action,
}: {
  projectId: string;
  assetId: string;
  mime: string;
  action: Action;
}) {
  const [url, setUrl] = useState("");
  return (
    <div className="style-player">
      {url ? (
        mime.startsWith("video/") ? (
          <video controls src={url} preload="metadata" />
        ) : (
          <audio controls src={url} preload="metadata" />
        )
      ) : (
        <Button
          variant="outline"
          onClick={() =>
            void action(async () => {
              const response = await request<{ url: string }>(
                `/projects/${projectId}/media/${assetId}/download?kind=proxy`,
              );
              setUrl(response.url);
            }, "Recording loaded")
          }
        >
          <Play size={15} /> Listen to the recording
        </Button>
      )}
      {url && (
        <button className="style-text-button" onClick={() => setUrl("")}>
          Refresh playback link
        </button>
      )}
    </div>
  );
}

export function SpeakerRoles({
  base,
  source,
  action,
  blocked,
}: {
  base: string;
  source: Source;
  action: Action;
  blocked: boolean;
}) {
  const roles = useQuery({
    queryKey: ["style-turns", source.id, "speakers"],
    queryFn: () =>
      request<{
        items: {
          speaker: string;
          labels: string[];
          roles: string[];
          turn_count: number;
          unassigned: number;
          overrides: number;
        }[];
        unassigned: number;
        missing_roles: string[];
      }>(`${base}/sources/${source.id}/speakers`),
    refetchInterval: 5000,
  });
  return (
    <section className="style-panel" aria-label="Speaker roles">
      <h2>Assign speaker roles</h2>
      <p>
        Set Speaker A, B, C and other labels once for the entire recording. This
        includes all conversation sections and pages. Sentence-level overrides
        stay unchanged.
      </p>
      <p className="style-help">
        Section labels such as “1: Speaker A” and “2: Speaker A” share this
        default. Check the voices; if a section uses the label for a different
        person, correct its sentences below.
      </p>
      {roles.error && <p role="alert">{roles.error.message}</p>}
      {roles.data?.items.map((g) => (
        <label
          key={g.speaker}
          className="style-panel"
          style={{ display: "block" }}
        >
          Speaker {g.speaker}
          <select
            aria-label={`Default role for speaker ${g.speaker}`}
            value={g.roles.length === 1 ? g.roles[0] : ""}
            disabled={blocked}
            onChange={(e) =>
              void action(
                () =>
                  request(
                    `${base}/sources/${source.id}/speakers`,
                    json("PATCH", {
                      speaker: g.speaker,
                      role: e.target.value,
                      across_sections: true,
                    }),
                  ),
                "Speaker role applied across the recording; local overrides preserved",
              )
            }
          >
            <option value="" disabled>
              {g.roles.length
                ? "Mixed roles — choose a default"
                : "Choose a default"}
            </option>
            <option value="unknown" disabled>
              Not assigned
            </option>
            <option value="interviewer">Interviewer</option>
            <option value="participant">Participant</option>
            <option value="other">Other</option>
          </select>
          <small>
            {g.turn_count} sentences · {g.unassigned} unassigned · {g.overrides}{" "}
            local overrides
          </small>
        </label>
      ))}
      {roles.data && (
        <p role="status">
          {roles.data.unassigned
            ? `${roles.data.unassigned} sentences still need a role. `
            : "All sentences have roles. "}
          {roles.data.missing_roles.length
            ? `Approval also needs: ${roles.data.missing_roles.join(" and ")}.`
            : "Interviewer and participant are identified."}
        </p>
      )}
    </section>
  );
}

export function Transcript({
  base,
  source,
  action,
  blocked,
  selected,
  setSelected,
  showSelection = true,
  showSpeakerPanel = true,
}: {
  base: string;
  source: Source;
  action: Action;
  blocked: boolean;
  selected: Turn[];
  setSelected: (turns: Turn[]) => void;
  showSelection?: boolean;
  showSpeakerPanel?: boolean;
}) {
  const [offset, setOffset] = useState(0);
  const [adding, setAdding] = useState(false);
  const turns = useQuery({
    queryKey: ["style-turns", source.id, offset],
    queryFn: () =>
      request<{ items: Turn[]; total: number }>(
        `${base}/sources/${source.id}/turns?offset=${offset}`,
      ),
    refetchInterval: 5000,
  });
  return (
    <>
      {showSpeakerPanel && (
        <SpeakerRoles
          base={base}
          source={source}
          action={action}
          blocked={blocked}
        />
      )}
      <div className="style-transcript">
        {turns.error && <p className="error">{turns.error.message}</p>}
        {turns.data?.items.map((t) => (
          <div
            className={`style-turn ${t.role === "interviewer" ? "is-interviewer" : ""}`}
            key={t.id}
          >
            {showSelection && (
              <label className="style-evidence-check">
                <input
                  type="checkbox"
                  checked={selected.some((s) => s.id === t.id)}
                  disabled={blocked}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? [...selected, t]
                        : selected.filter((s) => s.id !== t.id),
                    )
                  }
                />{" "}
                Select evidence · {time(t.start_ms)}–{time(t.end_ms)}
              </label>
            )}
            {!showSelection && (
              <p className="style-help">
                {time(t.start_ms)}–{time(t.end_ms)}
              </p>
            )}
            <TurnEditor
              key={`${t.id}-${source.revision}`}
              turn={t}
              base={base}
              source={source}
              action={action}
              blocked={blocked}
              onSaved={() => setSelected(selected.filter((s) => s.id !== t.id))}
            />
          </div>
        ))}
      </div>
      {(turns.data?.total || 0) > 50 && (
        <div className="style-pagination">
          <Button
            variant="outline"
            disabled={offset === 0}
            onClick={() => setOffset(offset - 50)}
          >
            Previous
          </Button>
          <span>
            {offset + 1}–{Math.min(offset + 50, turns.data!.total)} of{" "}
            {turns.data!.total}
          </span>
          <Button
            variant="outline"
            disabled={offset + 50 >= turns.data!.total}
            onClick={() => setOffset(offset + 50)}
          >
            Next
          </Button>
        </div>
      )}
      {!adding ? (
        <Button
          variant="outline"
          disabled={blocked}
          onClick={() => setAdding(true)}
        >
          <Plus size={14} /> Add transcript turn manually
        </Button>
      ) : (
        <div className="style-panel">
          <h3>Add a transcript turn</h3>
          <TurnEditor
            base={base}
            source={source}
            action={action}
            blocked={blocked}
            onSaved={() => setAdding(false)}
          />
          <button
            className="style-text-button"
            onClick={() => setAdding(false)}
          >
            Cancel
          </button>
        </div>
      )}
    </>
  );
}

function TurnEditor({
  turn,
  base,
  source,
  action,
  blocked,
  onSaved,
}: {
  turn?: Turn;
  base: string;
  source: Source;
  action: Action;
  blocked: boolean;
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState(!turn);
  const [role, setRole] = useState(turn?.role || "unknown");
  const [roleTouched, setRoleTouched] = useState(false);
  const [applyToSpeaker, setApplyToSpeaker] = useState(!turn?.role_override);
  const save = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    void action(async () => {
      await request(
        `${base}/sources/${source.id}/turns${turn ? `/${turn.id}` : ""}`,
        json(turn ? "PATCH" : "POST", {
          speaker: data.get("speaker"),
          role,
          role_scope: roleTouched
            ? applyToSpeaker
              ? "speaker"
              : "turn"
            : undefined,
          start_ms: Math.round(Number(data.get("start")) * 1000),
          end_ms: Math.round(Number(data.get("end")) * 1000),
          text: data.get("text"),
        }),
      );
      setEditing(false);
      onSaved();
    }, "Transcript saved; affected pattern approvals have been reset");
  };
  if (!editing && turn)
    return (
      <>
        <div className="style-turn-heading">
          <strong>{turn.speaker}</strong>
          <span className="status-pill">
            {turn.role}
            {turn.role_override ? " · local override" : ""}
          </span>
          <select
            aria-label={`Role for sentence at ${time(turn.start_ms)} by ${turn.speaker}`}
            value={turn.role}
            disabled={blocked}
            style={{ width: "auto", maxWidth: "100%", marginTop: 0 }}
            onChange={(e) => {
              const nextRole = e.target.value;
              void action(async () => {
                await request(
                  `${base}/sources/${source.id}/turns/${turn.id}`,
                  json("PATCH", {
                    speaker: turn.speaker,
                    role: nextRole,
                    start_ms: turn.start_ms,
                    end_ms: turn.end_ms,
                    text: turn.text,
                    role_scope: "turn",
                  }),
                );
                onSaved();
              }, "Sentence role updated; this local override is preserved");
            }}
          >
            <option value="unknown">Not assigned</option>
            <option value="interviewer">Interviewer</option>
            <option value="participant">Participant</option>
            <option value="other">Other</option>
          </select>
          <button
            className="style-text-button"
            disabled={blocked}
            onClick={() => setEditing(true)}
          >
            Edit words & role
          </button>
        </div>
        <p>{turn.text}</p>
      </>
    );
  return (
    <form onSubmit={save}>
      <div className="style-form-grid">
        <label>
          Speaker label
          <input
            name="speaker"
            required
            maxLength={80}
            defaultValue={turn?.speaker || "Speaker A"}
          />
        </label>
        <label>
          Speaker role
          <select
            value={role}
            onChange={(e) => {
              setRole(e.target.value as Turn["role"]);
              setRoleTouched(true);
            }}
          >
            <option value="unknown">Not identified</option>
            <option value="interviewer">Interviewer</option>
            <option value="participant">Participant</option>
            <option value="other">Other</option>
          </select>
        </label>
      </div>
      <label className="style-consent">
        <input
          type="checkbox"
          checked={applyToSpeaker}
          onChange={(e) => {
            setApplyToSpeaker(e.target.checked);
            setRoleTouched(true);
          }}
        />
        Apply role to all turns with this speaker label
      </label>
      <p className="style-help">
        On save, a role selection updates matching labels throughout this
        recording, except local overrides. Uncheck to change only this turn.
        Different section-prefixed labels remain separate; use the same label
        only after verifying the speaker.
      </p>
      <div className="style-form-grid">
        <label>
          Start (seconds)
          <input
            name="start"
            type="number"
            min="0"
            max={source.duration_ms / 1000}
            step="0.001"
            required
            defaultValue={(turn?.start_ms || 0) / 1000}
          />
        </label>
        <label>
          End (seconds)
          <input
            name="end"
            type="number"
            min="0.001"
            max={source.duration_ms / 1000}
            step="0.001"
            required
            defaultValue={turn ? turn.end_ms / 1000 : undefined}
          />
        </label>
      </div>
      <label>
        Transcript text
        <textarea
          name="text"
          required
          maxLength={8000}
          defaultValue={turn?.text}
        />
      </label>
      <Button disabled={blocked}>Save transcript turn</Button>
      {turn && (
        <button
          type="button"
          className="style-text-button"
          onClick={() => {
            setEditing(false);
            setRole(turn.role);
            setRoleTouched(false);
            setApplyToSpeaker(!turn.role_override);
          }}
        >
          Cancel
        </button>
      )}
    </form>
  );
}

function PatternCard({
  pattern,
  base,
  action,
  blocked,
}: {
  pattern: Pattern;
  base: string;
  action: Action;
  blocked: boolean;
}) {
  const [open, setOpen] = useState(false);
  const evidence = useQuery({
    queryKey: ["style", "evidence", pattern.id],
    queryFn: () => request<Turn[]>(`${base}/patterns/${pattern.id}/evidence`),
    enabled: open,
  });
  return (
    <article className="style-pattern">
      <div className="style-pattern-heading">
        <span className="tiny-label">{pattern.category}</span>
        <span
          className={`status-pill ${pattern.review_status === "approved" ? "style-approved" : ""}`}
        >
          {pattern.review_status}
        </span>
      </div>
      <h3>{pattern.instruction}</h3>
      <blockquote>{pattern.example}</blockquote>
      <p className="style-help">
        {pattern.evidence_ids.length} supporting turns ·{" "}
        {Math.round(pattern.confidence * 100)}%{" "}
        {pattern.origin === "manual" ? "reviewer" : "model"} confidence ·{" "}
        {pattern.origin === "manual" ? "Written by you" : "AI suggestion"}
      </p>
      <button className="style-text-button" onClick={() => setOpen(!open)}>
        {open ? "Close review" : "Review evidence & edit"}
      </button>
      {open && (
        <>
          {evidence.error && <p className="error">{evidence.error.message}</p>}
          {evidence.data && (
            <PatternEditor
              key={`${pattern.id}-${pattern.review_status}-${pattern.instruction}-${pattern.example}`}
              pattern={pattern}
              base={base}
              evidenceTurns={evidence.data}
              action={action}
              blocked={blocked}
            />
          )}
        </>
      )}
    </article>
  );
}

function PatternEditor({
  pattern,
  base,
  evidenceTurns,
  action,
  blocked,
  onSaved,
}: {
  pattern?: Pattern;
  base: string;
  evidenceTurns: Turn[];
  action: Action;
  blocked: boolean;
  onSaved?: () => void;
}) {
  const [anonymized, setAnonymized] = useState(false);
  const save = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const status =
      (e.nativeEvent as SubmitEvent).submitter?.getAttribute("value") ||
      "pending";
    void action(
      async () => {
        await request(
          pattern ? `${base}/style-drafts/${pattern.id}` : `${base}/patterns`,
          json(pattern ? "PATCH" : "POST", {
            category: data.get("category"),
            instruction: data.get("instruction"),
            example: data.get("example"),
            confidence: Number(data.get("confidence")) / 100,
            evidence_ids: evidenceTurns.map((t) => t.id),
            review_status: status,
            anonymized_confirmed: anonymized,
          }),
        );
        onSaved?.();
      },
      status === "approved" ? "Pattern approved" : "Pattern saved",
    );
  };
  return (
    <form onSubmit={save}>
      <div className="style-evidence">
        <h4>Supporting exchanges</h4>
        {evidenceTurns.map((t) => (
          <div key={t.id}>
            <span>
              {t.filename || "Selected recording"} · {time(t.start_ms)}–
              {time(t.end_ms)} · {t.role}
            </span>
            <p>{t.text}</p>
          </div>
        ))}
      </div>
      <div className="style-form-grid">
        <label>
          Behavior
          <select name="category" defaultValue={pattern?.category || "probe"}>
            {[
              "question",
              "acknowledgment",
              "probe",
              "transition",
              "closing",
            ].map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <label>
          Confidence (%)
          <input
            name="confidence"
            type="number"
            min={0}
            max={100}
            step={1}
            defaultValue={Math.round((pattern?.confidence ?? 0.5) * 100)}
            required
          />
        </label>
      </div>
      <label>
        Reusable style instruction
        <textarea
          name="instruction"
          defaultValue={pattern?.instruction}
          required
          maxLength={2000}
          placeholder="Describe an observable interviewing behavior."
        />
      </label>
      <label>
        Anonymized example
        <textarea
          name="example"
          defaultValue={pattern?.example}
          required
          maxLength={2000}
          placeholder="Write a generic example without source-specific names or facts."
        />
      </label>
      <label className="style-checkbox">
        <input
          type="checkbox"
          checked={anonymized}
          onChange={(e) => setAnonymized(e.target.checked)}
        />{" "}
        I checked the evidence, removed identifying facts, and excluded
        unconfirmed intentions.
      </label>
      <div className="modal-actions">
        <Button value="approved" disabled={blocked || !anonymized}>
          <Check size={14} /> Approve pattern
        </Button>
        <Button variant="outline" value="pending" disabled={blocked}>
          Save draft
        </Button>
        {pattern && (
          <Button variant="ghost" value="rejected" disabled={blocked}>
            Reject pattern
          </Button>
        )}
      </div>
    </form>
  );
}
