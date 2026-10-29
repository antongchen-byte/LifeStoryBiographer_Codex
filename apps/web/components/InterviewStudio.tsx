"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { request, type Project, type MediaAsset } from "../lib/api";
import { Button } from "./ui/button";
import MediaLibrary from "./MediaLibrary";
import InterviewAvatar from "./InterviewAvatar";
import InterviewMaterials, { type UploadOffer } from "./InterviewMaterials";

type Options = {
  avatars: Record<string, string>;
  personalities: Record<string, { label: string; description: string }>;
  genres: Record<string, string>;
  provider_ready: boolean;
  voice_ready: boolean;
};
type Config = {
  id: string;
  name: string;
  avatar: string;
  genre: string;
  project_id: string;
  created_at: string;
};
type Source = {
  id: string;
  filename: string;
  profile: string;
  revision: number;
  roles: string[];
  turn_count: number;
  preview: string;
};
type Turn = {
  id: string;
  request_id: string;
  sequence: number;
  role: string;
  text: string;
  original_text: string;
  state: string;
  error: string | null;
  has_audio: boolean;
  duration_ms: number | null;
  citations: { id: string; source: string; text: string }[];
  created_at: string;
};
type Interview = {
  id: string;
  project_id: string;
  upload_requests?: UploadOffer[];
  title: string;
  name: string;
  avatar: string;
  avatar_id: string;
  config_id: string;
  status: string;
  revision: number;
  model: string;
  busy: boolean;
  turns: Turn[];
  approvals: { id: string; revision: number }[];
};
const post = (body: unknown = {}) => ({
  method: "POST",
  body: JSON.stringify(body),
});
function download(name: string, value: string, type = "text/markdown") {
  const url = URL.createObjectURL(new Blob([value], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

export default function InterviewStudio({
  view = "setup",
  sessionId = "",
  begin = false,
}: {
  view?: "setup" | "conversation" | "review";
  sessionId?: string;
  begin?: boolean;
}) {
  const router = useRouter();
  const isSetup = view === "setup";
  const isReview = view === "review";
  const transcriptPanel = useRef<HTMLDivElement | null>(null);
  const openingPlayed = useRef(false);
  const cache = useQueryClient();
  const options = useQuery({
    queryKey: ["interview-options"],
    queryFn: () => request<Options>("/interviews/options"),
  });
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => request<Project[]>("/projects"),
  });
  const recommendations = useQuery({
    queryKey: ["interview-recommended-templates"],
    queryFn: () => request<{id: string; title: string; filename: string; markdown: string}[]>("/interviews/recommended-templates"),
  });
  const [recommended, setRecommended] = useState<string[]>(["life-story"]);
  const configs = useQuery({
    queryKey: ["interview-configs"],
    queryFn: () => request<Config[]>("/interviews/configs"),
  });
  const sessions = useQuery({
    queryKey: ["interview-sessions"],
    queryFn: () =>
      request<{ id: string; title: string; status: string }[]>(
        "/interviews/sessions",
      ),
  });
  const [project, setProject] = useState("");
  const [avatar, setAvatar] = useState("flame"),
    [name, setName] = useState("Ember"),
    [genre, setGenre] = useState("life_story");
  const [assets, setAssets] = useState<string[]>([]),
    [scripts, setScripts] = useState<Record<string, string>>({});
  const [sourceQuery, setSourceQuery] = useState(""),
    [sourceSearch, setSourceSearch] = useState("");
  const [nameEdited, setNameEdited] = useState(false);
  const [config, setConfig] = useState(""),
    [session, setSession] = useState(sessionId),
    [title, setTitle] = useState("My life story");
  const [consent, setConsent] = useState(false),
    [voice, setVoice] = useState(true),
    [text, setText] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [showSetup, setShowSetup] = useState(true),
    [recording, setRecording] = useState(false),
    [level, setLevel] = useState(0),
    [speaking, setSpeaking] = useState(false);
  const [audioUrl, setAudioUrl] = useState(""),
    [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [approvedQuery, setApprovedQuery] = useState(""),
    [approvedSearch, setApprovedSearch] = useState("");
  const recorder = useRef<MediaRecorder | null>(null),
    stream = useRef<MediaStream | null>(null),
    context = useRef<AudioContext | null>(null),
    animation = useRef(0),
    timer = useRef<ReturnType<typeof setTimeout> | null>(null),
    player = useRef<HTMLAudioElement | null>(null),
    audioSource = useRef<MediaElementAudioSourceNode | null>(null);
  const [handsFree, setHandsFree] = useState(false);
  const [voiceStarted, setVoiceStarted] = useState(false);
  const handsFreeRef = useRef(false);
  const resumeAfterUpload = useRef(false);
  const voiceActivity = useRef({
    started: 0,
    last: 0,
    previous: 0,
    speechMs: 0,
  });
  function pauseVoice() {
    handsFreeRef.current = false;
    setHandsFree(false);
    if (recorder.current?.state === "recording") recorder.current.stop();
    player.current?.pause();
    setSpeaking(false);
    setNotice(
      "Voice conversation paused. Any unsent recording can be reviewed or sent manually.",
    );
  }
  const [openingMic, setOpeningMic] = useState(false);
  const micGuard = useRef(false);
  const sendGuard = useRef(false),
    pendingRequest = useRef<string | null>(null);
  const media = useQuery({
    queryKey: ["media", project],
    queryFn: () => request<MediaAsset[]>(`/projects/${project}/media`),
    enabled: !!project,
    refetchInterval: 5000,
  });
  const sources = useQuery({
    queryKey: ["interview-sources", sourceSearch],
    queryFn: () =>
      request<Source[]>(
        `/interviews/sources?q=${encodeURIComponent(sourceSearch)}`,
      ),
  });
  const current = useQuery({
    queryKey: ["interview", session],
    queryFn: () => request<Interview>(`/interviews/sessions/${session}`),
    enabled: !!session,
    refetchInterval: session ? 4000 : false,
  });
  const approved = useQuery({
    queryKey: ["approved-interviews", project, approvedSearch],
    queryFn: () =>
      request<{ id: string; session_id: string; script: string }[]>(
        `/interviews/approved?project_id=${project}&q=${encodeURIComponent(approvedSearch)}`,
      ),
    enabled: !!project,
  });
  const s = current.data;
  const locked = busy || recording || openingMic || handsFree;
  useEffect(() => {
    if (!project && projects.data?.some((p) => p.role === "OWNER"))
      setProject(projects.data.find((p) => p.role === "OWNER")!.id);
  }, [project, projects.data]);
  useEffect(() => {
    if (view === "conversation" && transcriptPanel.current) {
      transcriptPanel.current.scrollTop = transcriptPanel.current.scrollHeight;
    }
  }, [view, s?.id, s?.turns.length]);
  useEffect(() => {
    if (
      !begin ||
      view !== "conversation" ||
      !s ||
      openingPlayed.current ||
      s.status !== "active"
    )
      return;
    openingPlayed.current = true;
    const opening = s.turns[0];
    if (opening?.role === "assistant") {
      setVoiceStarted(true);
      handsFreeRef.current = true;
      setHandsFree(true);
      void action(async () => {
        try {
          await playReply(opening, s.id);
        } catch (error) {
          handsFreeRef.current = false;
          setHandsFree(false);
          requestAnimationFrame(() =>
            document
              .getElementById("interview-input")
              ?.scrollIntoView({ block: "center" }),
          );
          throw error;
        }
      }, "After the opening speech, allow microphone access to answer. You can pause voice mode to type instead.");
    }
    // Start playback once on entry; subsequent replies are handled by the conversation loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [begin, view, s?.id]);
  useEffect(() => {
    audioSource.current?.disconnect();
    audioSource.current = null;
    void context.current?.close();
    context.current = null;
  }, [session]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (recording || recordedBlob || text.trim() || busy) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [recording, recordedBlob, text, busy]);
  useEffect(
    () => () => {
      if (audioUrl.startsWith("blob:")) URL.revokeObjectURL(audioUrl);
    },
    [audioUrl],
  );
  function stopMeter() {
    cancelAnimationFrame(animation.current);
    setLevel(0);
  }
  function meter(node: AudioNode) {
    stopMeter();
    const analyser = node.context.createAnalyser();
    analyser.fftSize = 256;
    node.connect(analyser);
    const data = new Uint8Array(analyser.fftSize);
    const update = () => {
      analyser.getByteTimeDomainData(data);
      const rms = Math.sqrt(
        data.reduce((sum, n) => sum + ((n - 128) / 128) ** 2, 0) / data.length,
      );
      setLevel(Math.min(1, rms * 6));
      if (handsFreeRef.current && recorder.current?.state === "recording") {
        const now = performance.now(),
          activity = voiceActivity.current;
        if (rms > 0.015) {
          activity.speechMs += Math.min(100, now - activity.previous);
          activity.last = now;
        }
        activity.previous = now;
        if (
          (activity.speechMs >= 350 && now - activity.last > 1600) ||
          (activity.speechMs < 350 && now - activity.started > 30000)
        ) {
          recorder.current.stop();
        }
      }
      animation.current = requestAnimationFrame(update);
    };
    update();
  }
  useEffect(
    () => () => {
      handsFreeRef.current = false;
      if (recorder.current?.state === "recording") {
        recorder.current.onstop = null;
        recorder.current.stop();
      }
      stream.current?.getTracks().forEach((t) => t.stop());
      if (timer.current) clearTimeout(timer.current);
      cancelAnimationFrame(animation.current);
      void context.current?.close();
    },
    [],
  );
  async function refresh() {
    await Promise.all([
      cache.invalidateQueries({ queryKey: ["interview"] }),
      cache.invalidateQueries({ queryKey: ["interview-sessions"] }),
      cache.invalidateQueries({ queryKey: ["interview-configs"] }),
      cache.invalidateQueries({ queryKey: ["approved-interviews"] }),
    ]);
  }
  async function action(work: () => Promise<unknown>, message = "Saved") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
      await refresh();
      setNotice(message);
      return true;
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Unable to complete this action",
      );
      await refresh();
      return false;
    } finally {
      setBusy(false);
    }
  }
  function chooseSession(id: string, beginInterview = false) {
    if (!id) return;
    handsFreeRef.current = false;
    setHandsFree(false);
    setVoiceStarted(false);
    player.current?.pause();
    setAudioUrl("");
    setSpeaking(false);
    stopMeter();
    setSession(id);
    localStorage.setItem("interview-active-session", id);
    setShowSetup(false);
    setRecordedBlob(null);
    pendingRequest.current = null;
    setText("");
    const status = sessions.data?.find((item) => item.id === id)?.status;
    router.push(
      `/interview-studio/${id}${!beginInterview && status && status !== "active" ? "/review" : ""}${beginInterview ? "?begin=1" : ""}`,
    );
  }
  async function playReply(turn: Turn, sessionId: string) {
    const automatic = handsFreeRef.current;
    const result = await request<{ url: string }>(
      `/interviews/sessions/${sessionId}/turns/${turn.id}/${turn.has_audio ? "audio" : "speech"}`,
      turn.has_audio ? undefined : post(),
    );
    if (!automatic || handsFreeRef.current) setAudioUrl(result.url);
  }
  useEffect(() => {
    if (audioUrl && player.current) {
      void player.current
        .play()
        .catch(() =>
          setNotice(
            "Audio is saved. Press Play below if your browser blocked autoplay.",
          ),
        );
    }
  }, [audioUrl]);
  async function startRecording(automatic = false) {
    if (micGuard.current) return;
    micGuard.current = true;
    setOpeningMic(true);
    setError("");
    player.current?.pause();
    setSpeaking(false);
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder)
        throw new Error(
          "Microphone recording requires a supported browser on localhost or HTTPS.",
        );
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (automatic && !handsFreeRef.current) {
        mic.getTracks().forEach((t) => t.stop());
        return;
      }
      stream.current = mic;
      context.current ??= new AudioContext();
      await context.current.resume();
      meter(context.current.createMediaStreamSource(mic));
      const mime = [
        "audio/webm;codecs=opus",
        "audio/mp4",
        "audio/ogg;codecs=opus",
      ].find((t) => MediaRecorder.isTypeSupported(t));
      if (!mime)
        throw new Error("This browser has no supported audio recorder format.");
      const rec = new MediaRecorder(mic, { mimeType: mime });
      recorder.current = rec;
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => {
        if (e.data.size) chunks.push(e.data);
      };
      rec.onerror = () => {
        handsFreeRef.current = false;
        setHandsFree(false);
        mic.getTracks().forEach((t) => t.stop());
        setRecording(false);
        stopMeter();
        setError(
          "Microphone recording failed. Voice conversation paused; review any captured audio before retrying.",
        );
      };
      rec.onstop = () => {
        mic.getTracks().forEach((t) => t.stop());
        stopMeter();
        setRecording(false);
        if (
          automatic &&
          handsFreeRef.current &&
          voiceActivity.current.speechMs < 350
        ) {
          handsFreeRef.current = false;
          setHandsFree(false);
          setNotice(
            "No speech detected. Voice conversation paused; check your microphone and try again.",
          );
        } else {
          setRecordedBlob(new Blob(chunks, { type: mime.split(";")[0] }));
        }
        pendingRequest.current = crypto.randomUUID();
        if (timer.current) clearTimeout(timer.current);
      };
      const started = performance.now();
      voiceActivity.current = {
        started,
        last: started,
        previous: started,
        speechMs: 0,
      };
      rec.start(1000);
      setRecording(true);
      setNotice(
        automatic
          ? "Listening. Pause briefly after your answer to send it automatically. The microphone closes while the interviewer replies."
          : "Recording this voice turn. It stops automatically after two minutes; you can then record another turn.",
      );
      timer.current = setTimeout(() => {
        if (rec.state === "recording") rec.stop();
      }, 120000);
    } catch (e) {
      stream.current?.getTracks().forEach((t) => t.stop());
      stopMeter();
      handsFreeRef.current = false;
      setHandsFree(false);
      setError(e instanceof Error ? e.message : "Microphone access failed");
    } finally {
      micGuard.current = false;
      setOpeningMic(false);
    }
  }
  async function send(retryId?: string) {
    if (!s || sendGuard.current) return;
    sendGuard.current = true;
    const sessionId = s.id;
    const automaticTurn = handsFreeRef.current;
    const saved = await action(async () => {
      const requestId =
        retryId || pendingRequest.current || crypto.randomUUID();
      pendingRequest.current = requestId;
      let body: Record<string, string> = { request_id: requestId };
      if (!retryId) {
        if (recordedBlob) {
          if (recordedBlob.size > 12 * 1024 ** 2)
            throw new Error(
              "This voice turn exceeds 12 MiB. Save the recording locally and record a shorter turn.",
            );
          const bytes = new Uint8Array(await recordedBlob.arrayBuffer());
          let binary = "";
          for (let i = 0; i < bytes.length; i += 32768)
            binary += String.fromCharCode(...bytes.subarray(i, i + 32768));
          body = { ...body, audio: btoa(binary), mime: recordedBlob.type };
        } else body.text = text;
      }
      const result = await request<Interview>(
        `/interviews/sessions/${sessionId}/turns`,
        post(body),
      );
      cache.setQueryData(["interview", sessionId], result);
      setText("");
      setRecordedBlob(null);
      pendingRequest.current = null;
      const uploadPending = result.upload_requests?.some(
        (offer) => offer.status === "pending",
      );
      if (uploadPending) {
        resumeAfterUpload.current = handsFreeRef.current;
        pauseVoice();
      }
      const reply = result.turns.at(-1);
      if (
        !uploadPending &&
        (automaticTurn ? handsFreeRef.current : voice) &&
        reply?.role === "assistant"
      ) {
        try {
          await playReply(reply, sessionId);
        } catch (e) {
          handsFreeRef.current = false;
          setHandsFree(false);
          setError(
            `Text reply saved. ${e instanceof Error ? e.message : "Voice output failed"}`,
          );
        }
      }
    }, "Conversation turn recorded");
    sendGuard.current = false;
    if (!saved) {
      handsFreeRef.current = false;
      setHandsFree(false);
    }
  }
  useEffect(() => {
    if (handsFree && recordedBlob && !busy && !sendGuard.current) void send();
    // Each completed recording is submitted once; sendGuard prevents overlapping calls.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordedBlob, handsFree, busy]);
  function onPlay() {
    setSpeaking(true);
    try {
      context.current ??= new AudioContext();
      void context.current.resume();
      if (!audioSource.current && player.current) {
        audioSource.current = context.current.createMediaElementSource(
          player.current,
        );
        audioSource.current.connect(context.current.destination);
      }
      if (audioSource.current) meter(audioSource.current);
    } catch {
      setLevel(0.35);
    }
  }
  const defaultAvatar = options.data?.avatars[avatar] || "Ember";
  return (
    <div className={`style-lab interview-studio interview-page-${view}`}>
      <div className="page-heading">
        <div>
          <p className="eyebrow">INTERVIEW STUDIO</p>
          <h1>
            {isSetup
              ? "A conversation worth keeping"
              : isReview
                ? "Review your interview"
                : s?.title || "Your interview"}
          </h1>
          <p>
            {isSetup
              ? "Choose an interviewer, bring your references, and tell your story."
              : isReview
                ? "Read the complete conversation, correct each turn, and approve the script when ready."
                : "Talk with your interviewer. Your recorded conversation appears alongside the avatar."}
          </p>
        </div>
      </div>
      {(error || options.error || configs.error || current.error) && (
        <p className="error" role="alert">
          {error ||
            options.error?.message ||
            configs.error?.message ||
            current.error?.message}
        </p>
      )}
      {notice && (
        <p className="style-notice" role="status">
          {notice}
        </p>
      )}
      {!isSetup && (
        <Button
          variant="outline"
          disabled={locked || !!recordedBlob || !!text.trim()}
          onClick={() => router.push("/interview-studio")}
        >
          Back to interviewer setup
        </Button>
      )}
      {isSetup && (
        <>
          <div className="interview-toolbar">
            <Button
              variant="outline"
              disabled={locked}
              onClick={() => setShowSetup(!showSetup)}
            >
              {showSetup
                ? "Hide interviewer setup"
                : "Configure an interviewer"}
            </Button>
            <label>
              Saved interviews
              <select
                value={session}
                disabled={locked || !!recordedBlob}
                onChange={(e) => chooseSession(e.target.value)}
              >
                <option value="">Choose an interview</option>
                {sessions.data?.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title} · {item.status}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {showSetup && (
            <section className="style-panel">
              <h2>1. Configure your interviewer</h2>
              <label>
                Biography workspace
                <select
                  value={project}
                  disabled={locked}
                  onChange={(e) => {
                    setProject(e.target.value);
                    setAssets([]);
                  }}
                >
                  <option value="">Choose a biography</option>
                  {projects.data
                    ?.filter((p) => p.role === "OWNER")
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.title}
                      </option>
                    ))}
                </select>
              </label>
              {!projects.data?.some((p) => p.role === "OWNER") && (
                <p>Create a biography workspace first from My biographies.</p>
              )}
              <div className="interview-avatar-options">
                {Object.entries(
                  options.data?.avatars || {
                    flame: "Ember",
                    female: "Maya",
                    male: "Eli",
                  },
                ).map(([kind, defaultName]) => (
                  <button
                    type="button"
                    key={kind}
                    className={
                      avatar === kind
                        ? "avatar-choice selected"
                        : "avatar-choice"
                    }
                    aria-pressed={avatar === kind}
                    disabled={locked}
                    onClick={() => {
                      setAvatar(kind);
                      if (!nameEdited && name === defaultAvatar) setName(defaultName);
                    }}
                  >
                    <InterviewAvatar kind={kind} name={defaultName} />
                    <strong>
                      {kind === "flame"
                        ? "Candle flame"
                        : kind === "female"
                          ? "Female face"
                          : "Male face"}
                    </strong>
                    <small>{defaultName}</small>
                    <p className="avatar-personality">
                      {options.data?.personalities[kind]?.label}
                    </p>
                  </button>
                ))}
              </div>
              <p aria-live="polite">
                {options.data?.personalities[avatar]?.description}
              </p>
              <div className="style-form-grid">
                <label>
                  Interviewer name
                  <input
                    value={name}
                    maxLength={100}
                    onChange={(e) => { setName(e.target.value); setNameEdited(true); }}
                  />
                </label>
                <label>
                  Interview genre
                  <select
                    value={genre}
                    onChange={(e) => setGenre(e.target.value)}
                  >
                    {Object.entries(options.data?.genres || {}).map(([key]) => (
                      <option key={key} value={key}>
                        {key.replaceAll("_", " ")}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <p>{options.data?.genres[genre]}</p>
              <p className="style-help">
                Each avatar has a distinct default personality. The genre sets
                the interview topic and approach; selected references further
                shape the style. These are AI avatars, not representations of
                real people.
              </p>
              <h3>Templates for style and retrieval</h3>
              <p>
                Upload one or more TXT, Markdown, PDF or Word documents. Select
                processed templates below. Their text is preserved in the
                configuration and used for in-context examples and keyword-based
                retrieval.
              </p>
              <details open>
                <summary>Select from recommended templates</summary>
                <p>Life story is selected by default. Choose one or more, or uncheck all to use only your own references.</p>
                {recommendations.error && <p role="alert">Unable to load recommended templates. Please refresh to try again.</p>}
                {recommendations.isPending && <p>Loading recommended templates…</p>}
                {recommendations.data?.map((template) => (
                  <div className="style-panel" key={template.id}>
                    <label className="interview-check">
                      <input type="checkbox" disabled={locked} checked={recommended.includes(template.id)}
                        onChange={(e) => setRecommended(e.target.checked ? [...recommended, template.id] : recommended.filter((id) => id !== template.id))} />
                      {template.title} · {template.filename}
                    </label>
                    <details><summary>Preview template</summary><pre style={{whiteSpace: "pre-wrap"}}>{template.markdown}</pre></details>
                    <Button variant="outline" onClick={() => download(template.filename, template.markdown)}>Download {template.filename}</Button>
                  </div>
                ))}
              </details>
              {project ? <MediaLibrary projectId={project} templatesOnly /> : <p>Select a biography workspace above to upload reference templates.</p>}
              <h4>Select uploaded templates</h4>
              <p>After processing finishes, check the documents to include in this interviewer.</p>
              <div className="interview-source-list">
                {media.data
                  ?.filter(
                    (a) =>
                      a.status === "ready" &&
                      (a.mime_type.startsWith("text/") ||
                        a.mime_type === "application/pdf" ||
                        a.mime_type.includes("wordprocessingml")),
                  )
                  .map((a) => (
                    <label key={a.id} className="interview-check">
                      <input
                        type="checkbox"
                        checked={assets.includes(a.id)}
                        onChange={(e) =>
                          setAssets(
                            e.target.checked
                              ? [...assets, a.id]
                              : assets.filter((id) => id !== a.id),
                          )
                        }
                      />
                      {a.original_filename}
                    </label>
                  ))}
              </div>
              <h3>Query saved scripts in PostgreSQL</h3>
              <form
                className="style-attach"
                onSubmit={(e) => {
                  e.preventDefault();
                  setSourceSearch(sourceQuery);
                }}
              >
                <label>
                  Find a script
                  <input
                    value={sourceQuery}
                    onChange={(e) => setSourceQuery(e.target.value)}
                    placeholder="Filename or words in the script"
                  />
                </label>
                <Button variant="outline">Search scripts</Button>
              </form>
              {sources.error && <p role="alert">{sources.error.message}</p>}
              <div className="interview-source-list">
                {sources.data?.map((a) => (
                  <div className="style-panel" key={a.id}>
                    <label className="interview-check">
                      <input
                        type="checkbox"
                        checked={a.id in scripts}
                        onChange={(e) => {
                          const next = { ...scripts };
                          if (e.target.checked)
                            next[a.id] = a.roles.includes("interviewer")
                              ? "interviewer"
                              : a.roles[0];
                          else delete next[a.id];
                          setScripts(next);
                        }}
                      />
                      {a.filename} · revision {a.revision} · {a.profile}
                    </label>
                    <p>{a.preview}</p>
                    {a.id in scripts && (
                      <label>
                        Role to learn from in {a.filename}
                        <select
                          value={scripts[a.id]}
                          onChange={(e) =>
                            setScripts({ ...scripts, [a.id]: e.target.value })
                          }
                        >
                          {a.roles.map((role) => (
                            <option key={role} value={role}>
                              {role}
                            </option>
                          ))}
                        </select>
                      </label>
                    )}
                  </div>
                ))}
              </div>
              {sources.data?.length === 0 && (
                <p>
                  No saved scripts match. Approve and save a Style Lab script
                  first, or continue with templates or a default genre.
                </p>
              )}
              <p className="style-help">
                Selected roles teach phrasing and question style; their life
                facts are not assumed to describe the new interviewee. Up to 12
                templates and 12 script selections per configuration.
              </p>
              <Button
                disabled={
                  locked ||
                  !project ||
                  !name.trim() ||
                  assets.length + recommended.length > 12 ||
                  Object.keys(scripts).length > 12
                }
                onClick={() =>
                  void action(async () => {
                    const result = await request<{
                      id: string;
                      filename: string;
                      markdown: string;
                    }>(
                      "/interviews/configs",
                      post({
                        project_id: project,
                        avatar,
                        name,
                        genre,
                        asset_ids: assets,
                        recommended_template_ids: recommended,
                        scripts: Object.entries(scripts).map(
                          ([archive_id, role]) => ({ archive_id, role }),
                        ),
                      }),
                    );
                    setConfig(result.id);
                    download(result.filename, result.markdown);
                  }, "Interviewer configuration saved; its Markdown file is ready in your downloads")
                }
              >
                Save interviewer & generate Markdown
              </Button>
            </section>
          )}
          <section className="style-panel">
            <h2>2. Start an interview</h2>
            <div className="style-form-grid">
              <label>
                Configured interviewer
                <select
                  value={config}
                  onChange={(e) => setConfig(e.target.value)}
                  disabled={locked}
                >
                  <option value="">Choose a configuration</option>
                  {configs.data?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ·{" "}
                      {c.avatar === "flame"
                        ? "Candle"
                        : c.avatar === "female"
                          ? "Female face"
                          : "Male face"}{" "}
                      · {c.genre.replaceAll("_", " ")} ·{" "}
                      {new Date(c.created_at).toLocaleString()} · #
                      {c.id.slice(0, 8)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Interview title
                <input
                  value={title}
                  maxLength={200}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
            </div>
            <label className="interview-check">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              I authorize sending selected references and this conversation to
              Gemini and recording its text and voice turns.
            </label>
            {!options.data?.provider_ready && (
              <p>
                Configure GEMINI_API_KEY and GEMINI_MODEL in the server .env
                before chatting.
              </p>
            )}
            <div className="interview-toolbar">
              <Button
                disabled={
                  locked ||
                  !!recordedBlob ||
                  !config ||
                  !title.trim() ||
                  (nameEdited && !name.trim()) ||
                  !consent ||
                  !options.data?.provider_ready
                }
                onClick={() =>
                  void action(async () => {
                    const result = await request<Interview>(
                      "/interviews/sessions",
                      post({
                        config_id: config,
                        title,
                        provider_consent: true,
                        start_with_greeting: true,
                        interviewer_name: nameEdited ? name.trim() : undefined,
                      }),
                    );
                    cache.setQueryData(["interview", result.id], result);
                    chooseSession(result.id, true);
                  }, "Your interviewer has started. Reply by typing or recording a voice turn.")
                }
              >
                Start interview
              </Button>
              <Button
                variant="outline"
                disabled={locked || !config}
                onClick={() =>
                  void action(async () => {
                    const file = await request<{
                      filename: string;
                      markdown: string;
                    }>(`/interviews/configs/${config}/markdown`);
                    download(file.filename, file.markdown);
                  }, "Configuration downloaded")
                }
              >
                Download interviewer Markdown
              </Button>
              <Button
                variant="destructive"
                disabled={locked || !config}
                onClick={() => {
                  if (
                    confirm(
                      "Delete this interviewer configuration? Delete its sessions first. Downloaded Markdown files remain on your computer.",
                    )
                  )
                    void action(async () => {
                      await request(`/interviews/configs/${config}`, {
                        method: "DELETE",
                      });
                      setConfig("");
                    }, "Configuration deleted");
                }}
              >
                Delete configuration
              </Button>
            </div>
          </section>
        </>
      )}
      {!isSetup && current.isLoading && (
        <p role="status">Loading your interview…</p>
      )}
      {!isSetup && s && (
        <section
          id="active-interview"
          className={`style-panel interview-session-layout ${s.status === "active" && !isReview ? "interview-active" : ""}`}
        >
          <aside
            className="interview-avatar-sidebar"
            aria-label="Interviewer avatar and playback"
          >
            <div className="interview-stage">
              <InterviewAvatar
                kind={s.avatar}
                name={s.name}
                level={level || (busy && !recording ? 0.2 : 0)}
                speaking={speaking || recording || busy}
              />
              <div>
                <h2>{s.name}</h2>
                <h3>{s.title}</h3>
                <p>
                  {recording
                    ? "Listening and recording…"
                    : speaking
                      ? "Speaking…"
                      : busy
                        ? "Working…"
                        : s.status === "active"
                          ? "Ready to listen"
                          : s.status === "review"
                            ? "Review the conversation"
                            : "Approved interview"}
                </p>
                <small>
                  Use case {s.config_id}
                  <br />
                  Avatar {s.avatar_id}
                </small>
                <p className="style-help">
                  Flame brightness and motion follow audio volume during
                  recording/playback. Text activity uses a simulated rhythm, not
                  emotion detection.
                </p>
              </div>
            </div>
            <audio
              key={session}
              ref={player}
              src={audioUrl || undefined}
              crossOrigin="anonymous"
              controls
              onPlay={onPlay}
              onPause={() => {
                setSpeaking(false);
                stopMeter();
              }}
              onEnded={() => {
                setSpeaking(false);
                stopMeter();
                if (handsFreeRef.current) {
                  document
                    .getElementById("interview-input")
                    ?.scrollIntoView({ behavior: "smooth", block: "center" });
                  void startRecording(true);
                }
              }}
              onError={() => {
                if (handsFreeRef.current) {
                  handsFreeRef.current = false;
                  setHandsFree(false);
                  setError(
                    "Voice playback failed. Conversation paused; your transcript is saved.",
                  );
                }
              }}
            />
          </aside>
          <div className="interview-conversation-workspace">
            <InterviewMaterials
              sessionId={s.id}
              projectId={s.project_id}
              status={s.status}
              offers={s.upload_requests || []}
              disabled={busy || openingMic}
              onSessionChange={(value) =>
                cache.setQueryData(["interview", s.id], value as Interview)
              }
              onOpen={() => {
                resumeAfterUpload.current =
                  resumeAfterUpload.current || handsFreeRef.current;
                pauseVoice();
              }}
              onDiscussion={(value) => {
                const updated = value as Interview;
                const latest = updated.turns.at(-1);
                if (resumeAfterUpload.current && s.status === "active") {
                  resumeAfterUpload.current = false;
                  handsFreeRef.current = true;
                  setHandsFree(true);
                  setVoiceStarted(true);
                }
                if (latest && (handsFreeRef.current || voice))
                  void playReply(latest, s.id).catch((e) => {
                    pauseVoice();
                    setError(
                      e instanceof Error
                        ? e.message
                        : "Unable to play material discussion. Read it in the conversation below.",
                    );
                  });
              }}
              onClose={() => {
                if (resumeAfterUpload.current && s.status === "active") {
                  resumeAfterUpload.current = false;
                  handsFreeRef.current = true;
                  setHandsFree(true);
                  setVoiceStarted(true);
                  if (!recordedBlob) void startRecording(true);
                }
              }}
            />
            {isReview && s.status === "active" && (
              <p role="alert">
                Save this conversation for review before editing.{" "}
                <button
                  onClick={() => router.push(`/interview-studio/${s.id}`)}
                >
                  Return to conversation
                </button>
              </p>
            )}
            <div
              ref={transcriptPanel}
              role="log"
              aria-live={isReview ? "off" : "polite"}
              className="interview-conversation"
              aria-label="Interview conversation"
            >
              {s.turns.map((t) => (
                <article className={`interview-turn ${t.role}`} key={t.id}>
                  <header>
                    <strong>{t.role === "assistant" ? s.name : "You"}</strong>
                    <small>
                      {new Date(t.created_at).toLocaleTimeString()} · {t.state}
                    </small>
                  </header>
                  <p>
                    {t.text || "Voice recording saved; transcription pending."}
                  </p>
                  {t.error && <p className="error">{t.error}</p>}
                  {t.has_audio && (
                    <Button
                      variant="outline"
                      disabled={locked}
                      onClick={() =>
                        void action(async () => {
                          const result = await request<{ url: string }>(
                            `/interviews/sessions/${s.id}/turns/${t.id}/audio`,
                          );
                          setAudioUrl(result.url);
                        }, "Recording loaded")
                      }
                    >
                      Play saved audio
                    </Button>
                  )}
                  {t.role === "assistant" &&
                    !t.has_audio &&
                    s.status === "active" && (
                      <Button
                        variant="outline"
                        disabled={locked || !options.data?.voice_ready}
                        onClick={() =>
                          void action(
                            () => playReply(t, s.id),
                            "Voice reply saved",
                          )
                        }
                      >
                        Speak & record reply
                      </Button>
                    )}
                  {t.role === "user" &&
                    t.state !== "complete" &&
                    s.status === "active" && (
                      <Button
                        disabled={locked}
                        onClick={() => void send(t.request_id)}
                      >
                        Retry this turn
                      </Button>
                    )}
                  {!!t.citations.length && (
                    <details>
                      <summary>Reference material used</summary>
                      {t.citations.map((c) => (
                        <blockquote key={c.id}>
                          <strong>{c.source}</strong>
                          <p>{c.text}</p>
                        </blockquote>
                      ))}
                    </details>
                  )}
                  {isReview && s.status === "review" && (
                    <ReviewTurn
                      turn={t}
                      disabled={locked}
                      save={(value) =>
                        action(
                          () =>
                            request(
                              `/interviews/sessions/${s.id}/turns/${t.id}`,
                              {
                                method: "PATCH",
                                body: JSON.stringify({
                                  text: value,
                                  revision: s.revision,
                                }),
                              },
                            ),
                          "Transcript correction saved; original text and audio retained",
                        )
                      }
                    />
                  )}
                </article>
              ))}
            </div>
            {!isReview && s.status === "active" && (
              <>
                <div id="interview-input" className="interview-input-panel">
                  <h3>Your turn</h3>
                  <div className="interview-toolbar">
                    <Button
                      disabled={!handsFree && (locked || !!text.trim())}
                      onClick={() => {
                        if (handsFreeRef.current) pauseVoice();
                        else {
                          setVoiceStarted(true);
                          handsFreeRef.current = true;
                          setHandsFree(true);
                          setVoice(true);
                          if (!recordedBlob) void startRecording(true);
                        }
                      }}
                    >
                      {handsFree
                        ? "Pause voice conversation"
                        : voiceStarted
                          ? "Resume voice conversation"
                          : "Start voice conversation"}
                    </Button>
                    {handsFree && recording && (
                      <Button
                        variant="outline"
                        onClick={() => recorder.current?.stop()}
                      >
                        Send voice answer now
                      </Button>
                    )}
                  </div>
                  {voiceStarted && !handsFree && (
                    <p role="status">
                      Voice conversation paused. Resume continues this interview
                      {recordedBlob
                        ? " and sends your unsent recording first"
                        : ""}
                      , or save it for review.
                    </p>
                  )}
                  <details className="voice-help">
                    <summary>How voice conversation works</summary>
                    <p className="style-help">
                      Voice conversation listens for your answer, sends it after
                      a short pause, speaks the interviewer's reply, then
                      listens again. Pause at any time. Headphones help prevent
                      echo; background noise may require “Send voice answer
                      now”. Gemini transcription and speech access are required.
                    </p>
                  </details>
                  <label className="interview-check">
                    <input
                      type="checkbox"
                      checked={voice}
                      onChange={(e) => setVoice(e.target.checked)}
                    />
                    Speak replies and retain generated audio (uses
                    GEMINI_TTS_MODEL)
                  </label>
                  <label>
                    Your message
                    <textarea
                      value={text}
                      maxLength={16000}
                      disabled={locked || !!recordedBlob}
                      onChange={(e) => {
                        setText(e.target.value);
                        pendingRequest.current = null;
                      }}
                      placeholder="Tell me about a memory…"
                    />
                  </label>
                  <div className="interview-toolbar">
                    <Button
                      disabled={locked || (!text.trim() && !recordedBlob)}
                      onClick={() => void send()}
                    >
                      {recordedBlob
                        ? "Send recorded voice turn"
                        : "Send message"}
                    </Button>
                    <Button
                      variant="outline"
                      disabled={
                        busy || openingMic || !!recordedBlob || !!text.trim()
                      }
                      onClick={() => {
                        if (recording) recorder.current?.stop();
                        else void startRecording();
                      }}
                    >
                      {openingMic
                        ? "Opening microphone…"
                        : recording
                          ? "Stop recording"
                          : "Record voice turn"}
                    </Button>
                    {recordedBlob && (
                      <>
                        <Button
                          variant="outline"
                          onClick={() => {
                            const url = URL.createObjectURL(recordedBlob);
                            setAudioUrl(url);
                          }}
                        >
                          Preview voice turn
                        </Button>
                        <Button
                          variant="outline"
                          onClick={() => {
                            const extension = recordedBlob.type.includes("mp4")
                              ? "m4a"
                              : recordedBlob.type.includes("ogg")
                                ? "ogg"
                                : "webm";
                            const url = URL.createObjectURL(recordedBlob);
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = `unsent-voice-turn.${extension}`;
                            a.click();
                            setTimeout(() => URL.revokeObjectURL(url), 10000);
                          }}
                        >
                          Save unsent recording locally
                        </Button>
                        <Button
                          variant="outline"
                          disabled={busy}
                          onClick={() => {
                            if (confirm("Discard this unsent recording?")) {
                              setRecordedBlob(null);
                              pendingRequest.current = null;
                            }
                          }}
                        >
                          Discard unsent recording
                        </Button>
                      </>
                    )}
                  </div>
                  <p className="style-help">
                    Voice turns are recorded in full, up to two minutes each.
                    Send the turn to save it on the server before leaving this
                    page. Both microphone recordings and generated voice replies
                    can be replayed later.
                  </p>
                  <Button
                    variant="outline"
                    disabled={busy || recording || openingMic}
                    onClick={() => {
                      pauseVoice();
                      void action(async () => {
                        let draft: Record<string, string> | undefined;
                        if (recordedBlob || text.trim()) {
                          const request_id =
                            pendingRequest.current || crypto.randomUUID();
                          pendingRequest.current = request_id;
                          if (recordedBlob) {
                            if (recordedBlob.size > 12 * 1024 ** 2)
                              throw new Error(
                                "Recording exceeds 12 MiB; save it locally before continuing.",
                              );
                            const bytes = new Uint8Array(
                              await recordedBlob.arrayBuffer(),
                            );
                            let binary = "";
                            for (let i = 0; i < bytes.length; i += 32768)
                              binary += String.fromCharCode(
                                ...bytes.subarray(i, i + 32768),
                              );
                            draft = {
                              request_id,
                              audio: btoa(binary),
                              mime: recordedBlob.type,
                            };
                          } else draft = { request_id, text };
                        }
                        const result = await request<Interview>(
                          `/interviews/sessions/${s.id}/finish`,
                          post({ draft }),
                        );
                        cache.setQueryData(["interview", s.id], result);
                        setRecordedBlob(null);
                        setText("");
                        pendingRequest.current = null;
                      }, "Conversation saved for review. Any untranscribed recording is retained; fill in its transcript before approval.");
                    }}
                  >
                    Save conversation for review
                  </Button>
                </div>
              </>
            )}
            {!isReview && s.status !== "active" && (
              <div className="style-panel">
                <p role="status">
                  Your conversation has been saved. Open the review page to read
                  and edit the full transcript.
                </p>
                <Button
                  onClick={() =>
                    router.push(`/interview-studio/${s.id}/review`)
                  }
                >
                  Start to review interview
                </Button>
              </div>
            )}
            {isReview && s.status === "review" && (
              <div className="style-panel">
                <p>
                  Read every turn and correct transcription errors above.
                  Original wording and recordings are retained alongside your
                  corrections. Approval freezes this revision for screenplay
                  retrieval.
                </p>
                <Button
                  disabled={
                    locked ||
                    !s.turns.length ||
                    s.turns.some((t) => !t.text.trim())
                  }
                  onClick={() =>
                    void action(
                      () =>
                        request(
                          `/interviews/sessions/${s.id}/approve`,
                          post({ revision: s.revision }),
                        ),
                      "Interview approved and stored in the separate interview database",
                    )
                  }
                >
                  Approve conversation script
                </Button>
              </div>
            )}
            {process.env.NEXT_PUBLIC_ENABLE_FILM_STUDIOS !== "false" && s.status !== "active" && (
              <Button
                variant="outline"
                onClick={() =>
                  router.push(`/screenplay-editor?interview=${s.id}`)
                }
              >
                Proceed to Screenplay Editor
              </Button>
            )}
            {s.status === "approved" && (
              <Button
                onClick={() =>
                  void action(async () => {
                    const result = await request<{
                      filename: string;
                      markdown: string;
                      snapshot: unknown;
                    }>(`/interviews/sessions/${s.id}/export`);
                    download(`${result.filename}.md`, result.markdown);
                    download(
                      `${result.filename}.json`,
                      JSON.stringify(result.snapshot, null, 2),
                      "application/json",
                    );
                  }, "Approved script exported")
                }
              >
                Download approved script
              </Button>
            )}
            <Button
              variant="destructive"
              disabled={locked || !!recordedBlob}
              onClick={() => {
                if (
                  confirm(
                    "Delete this interview, its recordings and approved script? Downloaded files remain on your computer.",
                  )
                )
                  void action(async () => {
                    await request(`/interviews/sessions/${s.id}`, {
                      method: "DELETE",
                    });
                    setSession("");
                    localStorage.removeItem("interview-active-session");
                    setAudioUrl("");
                    router.push("/interview-studio");
                  }, "Interview deleted");
              }}
            >
              Delete interview
            </Button>
          </div>
        </section>
      )}
      {isSetup && (
        <section className="style-panel">
          <h2>Approved interviews for future screenplays</h2>
          <p>
            Only approved conversations appear here. These live in the separate{" "}
            <code>biographer_interviews</code> PostgreSQL database.
          </p>
          <form
            className="style-attach"
            onSubmit={(e) => {
              e.preventDefault();
              setApprovedSearch(approvedQuery);
            }}
          >
            <label>
              Search approved conversation scripts
              <input
                value={approvedQuery}
                onChange={(e) => setApprovedQuery(e.target.value)}
              />
            </label>
            <Button disabled={!project}>Search approved interviews</Button>
          </form>
          {approved.error && <p role="alert">{approved.error.message}</p>}
          {approved.data?.map((item) => (
            <details key={item.id}>
              <summary>Approved interview {item.session_id}</summary>
              <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                {item.script}
              </pre>
              <Button
                variant="outline"
                disabled={locked || !!recordedBlob}
                onClick={() => chooseSession(item.session_id)}
              >
                Open approved interview
              </Button>
            </details>
          ))}
        </section>
      )}
    </div>
  );
}
function ReviewTurn({
  turn,
  disabled,
  save,
}: {
  turn: Turn;
  disabled: boolean;
  save: (value: string) => Promise<boolean>;
}) {
  const [editing, setEditing] = useState(false),
    [value, setValue] = useState(turn.text);
  return editing ? (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void save(value).then((saved) => {
          if (saved) setEditing(false);
        });
      }}
    >
      <label>
        Corrected text for turn {turn.sequence}
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          required
          maxLength={16000}
        />
      </label>
      <Button disabled={disabled}>Save correction</Button>
      <Button variant="outline" type="button" onClick={() => setEditing(false)}>
        Cancel
      </Button>
    </form>
  ) : (
    <Button
      variant="outline"
      disabled={disabled}
      onClick={() => {
        setValue(turn.text);
        setEditing(true);
      }}
    >
      Edit transcript turn
    </Button>
  );
}
