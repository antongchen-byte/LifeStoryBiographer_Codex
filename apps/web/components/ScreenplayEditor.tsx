"use client";
import PhotoCrop from "./PhotoCrop";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { request, type Project, type MediaAsset } from "../lib/api";
import { Button } from "./ui/button";
import MediaLibrary from "./MediaLibrary";

type Element = {
  kind:
    | "scene"
    | "action"
    | "character"
    | "parenthetical"
    | "dialogue"
    | "transition";
  text: string;
};
type Content = { elements: Element[]; material_ids: string[]; notes: string };
type Subsection = {
  id: string;
  position: number;
  seconds: 10 | 15;
  start_seconds: number;
  content: Content;
};
type Section = {
  id: string;
  position: number;
  seconds: number;
  content: Content;
  subsections: Subsection[];
  breakdown_stale: boolean;
};
type Material = {
  mime_type?: string;
  id: string;
  filename: string;
  asset_id: string;
  editor_notes?: string;
  confirmation?: { description?: string };
  analysis?: { summary?: string };
};
type Screenplay = {
  id: string;
  title: string;
  interview_uid: string;
  project_id: string;
  session_id: string | null;
  source: { notice?: string };
  reviewed_markdown: string;
  materials: Material[];
  revision: number;
  state: string;
  sections: Section[];
  progress: number;
  error?: string;
  draft_stale: boolean;
  job_kind?: string;
  exports: { revision: number }[];
};
const ACTIVE = ["pending", "dispatched", "running"];
const post = (data: unknown = {}) => ({
  method: "POST",
  body: JSON.stringify(data),
});

function ContentEditor({
  value,
  onChange,
  label,
  materials,
  disabled,
}: {
  value: Content;
  onChange: (v: Content) => void;
  label: string;
  materials: Material[];
  disabled: boolean;
}) {
  const patch = (index: number, change: Partial<Element>) =>
    onChange({
      ...value,
      elements: value.elements.map((e, i) =>
        i === index ? { ...e, ...change } : e,
      ),
    });
  return (
    <fieldset disabled={disabled} className="screenplay-content-editor">
      <legend>{label}</legend>
      {value.elements.map((element, index) => (
        <div className="screenplay-element-editor" key={index}>
          <label>
            Element {index + 1}
            <select
              aria-label={`${label} element ${index + 1} type`}
              value={element.kind}
              onChange={(e) =>
                patch(index, { kind: e.target.value as Element["kind"] })
              }
            >
              {[
                "scene",
                "action",
                "character",
                "parenthetical",
                "dialogue",
                "transition",
              ].map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
          <label className="screenplay-element-text">
            Text
            <textarea
              aria-label={`${label} element ${index + 1} text`}
              value={element.text}
              rows={2}
              maxLength={3000}
              onChange={(e) => patch(index, { text: e.target.value })}
            />
          </label>
          <Button
            variant="outline"
            disabled={value.elements.length <= 1}
            onClick={() =>
              onChange({
                ...value,
                elements: value.elements.filter((_, i) => i !== index),
              })
            }
          >
            Remove element
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        disabled={value.elements.length >= 50}
        onClick={() =>
          onChange({
            ...value,
            elements: [...value.elements, { kind: "action", text: "" }],
          })
        }
      >
        Add element
      </Button>
      <label>
        Production notes / proposed staging
        <textarea
          aria-label={`${label} production notes`}
          value={value.notes}
          maxLength={4000}
          onChange={(e) => onChange({ ...value, notes: e.target.value })}
        />
      </label>
      {materials.length > 0 && (
        <fieldset>
          <legend>Supporting materials for {label}</legend>
          {materials.map((m) => (
            <label className="screenplay-material-choice" key={m.id}>
              <input
                type="checkbox"
                checked={value.material_ids.includes(m.id)}
                onChange={(e) =>
                  onChange({
                    ...value,
                    material_ids: e.target.checked
                      ? [...value.material_ids, m.id]
                      : value.material_ids.filter((id) => id !== m.id),
                  })
                }
              />
              {m.filename}
            </label>
          ))}
        </fieldset>
      )}
      <details>
        <summary>Formatted preview</summary>
        <div className="screenplay-paper">
          {value.elements.map((e, i) => (
            <p key={i} className={`screenplay-${e.kind}`}>
              {e.text}
            </p>
          ))}
        </div>
      </details>
    </fieldset>
  );
}

export default function ScreenplayEditor({
  initialInterview,
  initialScreenplay,
}: {
  initialInterview?: string;
  initialScreenplay?: string;
}) {
  const cache = useQueryClient();
  const [id, setId] = useState(initialScreenplay || "");
  const [draft, setDraft] = useState<Screenplay | null>(null);
  const [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [interview, setInterview] = useState(initialInterview || ""),
    [project, setProject] = useState("");
  const [sourceFile, setSourceFile] = useState<{
    name: string;
    text: string;
  } | null>(null);
  const [consent, setConsent] = useState(false),
    [pages, setPages] = useState(3),
    [seconds, setSeconds] = useState<10 | 15>(10);
  const [selected, setSelected] = useState<string[]>([]);
  const started = useRef(false);
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => request<Project[]>("/projects"),
  });
  const interviews = useQuery({
    queryKey: ["screenplay-interviews"],
    queryFn: () =>
      request<{ id: string; title: string; status: string }[]>(
        "/interviews/sessions",
      ),
  });
  const saved = useQuery({
    queryKey: ["screenplays"],
    queryFn: () =>
      request<{ id: string; title: string; interview_uid: string }[]>(
        "/interviews/screenplays",
      ),
  });
  const current = useQuery({
    queryKey: ["screenplay", id],
    queryFn: () => request<Screenplay>(`/interviews/screenplays/${id}`),
    enabled: !!id,
    refetchInterval: (q) =>
      ACTIVE.includes((q.state.data as Screenplay | undefined)?.state || "")
        ? 2000
        : false,
  });
  const media = useQuery({
    queryKey: ["media", draft?.project_id],
    queryFn: () =>
      request<MediaAsset[]>(`/projects/${draft!.project_id}/media`),
    enabled: !!draft,
    refetchInterval: 5000,
  });
  useEffect(() => {
    if (current.data && !dirty) setDraft(current.data);
  }, [current.data, dirty]);
  function update(value: Screenplay) {
    setId(value.id);
    setDraft(value);
    setDirty(false);
    cache.setQueryData(["screenplay", value.id], value);
    void cache.invalidateQueries({ queryKey: ["screenplays"] });
    window.history.replaceState(
      null,
      "",
      `/screenplay-editor?screenplay=${value.id}`,
    );
  }
  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Unable to complete this action",
      );
    } finally {
      setBusy(false);
    }
  }
  const canSwitch = () =>
    !dirty || confirm("Discard unsaved screenplay edits and switch sources?");
  async function loadInterview(uid: string) {
    await act(async () => {
      update(
        await request<Screenplay>(
          "/interviews/screenplays",
          post({ session_id: uid }),
        ),
      );
      setNotice(
        "Interview loaded. Review the conversation and materials before generating.",
      );
    });
  }
  useEffect(() => {
    if (initialInterview && !initialScreenplay && !started.current) {
      started.current = true;
      void loadInterview(initialInterview);
    }
  }, [initialInterview, initialScreenplay]); // Initial handoff only.
  function edit(value: Screenplay) {
    setDraft(value);
    setDirty(true);
  }
  function saveBody(s: Screenplay) {
    return {
      revision: s.revision,
      title: s.title,
      reviewed_markdown: s.reviewed_markdown,
      material_notes: Object.fromEntries(
        s.materials.map((m) => [m.id, m.editor_notes || ""]),
      ),
      sections: s.sections.map((p) => ({
        id: p.id,
        content: p.content,
        subsections: p.subsections.map((sub) => ({
          id: sub.id,
          seconds: sub.seconds,
          content: sub.content,
        })),
      })),
    };
  }
  async function persist() {
    if (!draft) throw new Error("Load a source first");
    const value = await request<Screenplay>(`/interviews/screenplays/${id}`, {
      method: "PUT",
      body: JSON.stringify(saveBody(draft)),
    });
    update(value);
    return value;
  }
  async function generate(kind: "draft" | "breakdown") {
    if (!draft) return;
    if (
      (kind === "draft" && draft.sections.length) ||
      (kind === "breakdown" && draft.sections.some((p) => p.subsections.length))
    ) {
      if (
        !confirm(
          `Regenerate ${kind === "draft" ? "the screenplay and its subsections" : "subsections"}? The new result will replace their saved edits only if generation succeeds.`,
        )
      )
        return;
    }
    await act(async () => {
      const value = dirty ? await persist() : draft;
      update(
        await request<Screenplay>(
          `/interviews/screenplays/${id}/generate`,
          post({
            revision: value.revision,
            kind,
            sections: pages,
            seconds,
            consent,
          }),
        ),
      );
      setNotice(
        "Generation queued. You may leave this page and reopen the saved screenplay.",
      );
    });
  }
  function pageChange(index: number, content: Content) {
    if (draft)
      edit({
        ...draft,
        sections: draft.sections.map((p, i) =>
          i === index ? { ...p, content } : p,
        ),
      });
  }
  function subChange(pi: number, si: number, content: Content) {
    if (draft)
      edit({
        ...draft,
        sections: draft.sections.map((p, i) =>
          i === pi
            ? {
                ...p,
                subsections: p.subsections.map((sub, j) =>
                  j === si ? { ...sub, content } : sub,
                ),
              }
            : p,
        ),
      });
  }
  const running = !!draft && ACTIVE.includes(draft.state),
    locked = busy || running;
  const generationProgress =
    running && draft ? (
      <div role="status">
        <p>
          {draft.job_kind === "breakdown"
            ? "Preparing video subsections"
            : "Writing screenplay"}
          … {draft.progress}%
        </p>
        <progress max={100} value={draft.progress || undefined} />
        <Button
          variant="outline"
          onClick={() =>
            void act(async () => {
              update(
                await request<Screenplay>(
                  `/interviews/screenplays/${id}/stop`,
                  post(),
                ),
              );
              setNotice(
                "Generation stopped. An in-flight provider call may finish, but its result will not replace your edits.",
              );
            })
          }
        >
          Stop generation
        </Button>
      </div>
    ) : null;
  return (
    <main className="screenplay-editor">
      <header>
        <p className="eyebrow">SCREENPLAY EDITOR</p>
        <h1>Shape your story for the screen</h1>
        <p>
          Review your conversation, create one-minute sections, then prepare
          short video subsections.
        </p>
      </header>
      <section className="screenplay-panel">
        <h2>Open a source</h2>
        <label>
          Database interview
          <select
            value={interview}
            onChange={(e) => setInterview(e.target.value)}
          >
            <option value="">Choose an interview</option>
            {interviews.data
              ?.filter((i) => i.status !== "active")
              .map((i) => (
                <option key={i.id} value={i.id}>
                  {i.title} · {i.id} · {i.status}
                </option>
              ))}
          </select>
        </label>
        <Button
          disabled={locked || !interview}
          onClick={() => {
            if (canSwitch()) void loadInterview(interview);
          }}
        >
          Load interview
        </Button>
        <details>
          <summary>Import a saved Markdown file</summary>
          <p>
            Filenames in Markdown do not load local images automatically. Attach
            those materials after importing.
          </p>
          <label>
            Biography workspace
            <select
              value={project}
              onChange={(e) => setProject(e.target.value)}
            >
              <option value="">Choose a workspace</option>
              {projects.data
                ?.filter((p) => p.role === "OWNER")
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title || p.subject_name}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Saved interview Markdown
            <input
              type="file"
              accept=".md,text/markdown"
              disabled={locked}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                setSourceFile(null);
                void act(async () => {
                  if (file.size > 800000)
                    throw new Error("Choose a Markdown file under 800 KB");
                  const text = await file.text();
                  if (text.length > 200000)
                    throw new Error("Source exceeds 200,000 characters");
                  setSourceFile({ name: file.name, text });
                });
              }}
            />
          </label>
          <Button
            disabled={locked || !sourceFile || !project}
            onClick={() => {
              if (canSwitch())
                void act(async () => {
                  update(
                    await request<Screenplay>(
                      "/interviews/screenplays",
                      post({
                        project_id: project,
                        markdown: sourceFile!.text,
                        filename: sourceFile!.name,
                      }),
                    ),
                  );
                  setNotice(
                    "Markdown imported. Review it and attach any supporting files.",
                  );
                });
            }}
          >
            Load Markdown
          </Button>
        </details>
        <label>
          Saved screenplay
          <select
            value={id}
            disabled={locked}
            onChange={(e) => {
              if (canSwitch()) {
                setDirty(false);
                setDraft(null);
                setId(e.target.value);
                setNotice("");
              }
            }}
          >
            <option value="">Choose a saved screenplay</option>
            {saved.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title} · {s.interview_uid} · {s.id.slice(0, 8)}
              </option>
            ))}
          </select>
        </label>
        {(interviews.error || saved.error || projects.error) && (
          <p role="alert">
            Unable to load sources. Refresh and check that you are signed in.
          </p>
        )}
      </section>
      {(error || current.error) && (
        <p role="alert">
          {error || current.error?.message}{" "}
          {current.error && (
            <Button onClick={() => void current.refetch()}>
              Retry loading
            </Button>
          )}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {current.isFetching && !draft && <p role="status">Loading screenplay…</p>}
      {draft && (
        <>
          <section className="screenplay-panel">
            <h2>1. Review conversation and materials</h2>
            <p>
              Interview UID: <code>{draft.interview_uid}</code>
              <br />
              Screenplay UID: <code>{draft.id}</code> · Revision{" "}
              {draft.revision}
            </p>
            {draft.source.notice && <p>{draft.source.notice}</p>}
            <label>
              Screenplay title
              <input
                value={draft.title}
                maxLength={200}
                disabled={locked}
                onChange={(e) => edit({ ...draft, title: e.target.value })}
              />
            </label>
            <label>
              Conversation Markdown
              <textarea
                rows={12}
                maxLength={200000}
                disabled={locked}
                value={draft.reviewed_markdown}
                onChange={(e) =>
                  edit({ ...draft, reviewed_markdown: e.target.value })
                }
              />
            </label>
            <p>
              Changes here are saved for this screenplay. The original interview
              and approved script are preserved.
            </p>
            <details>
              <summary>
                Review supporting materials ({draft.materials.length})
              </summary>
              {draft.materials.map((m, i) => (
                <div key={m.id} className="screenplay-material">
                  <strong>{m.filename}</strong>
                  {m.mime_type?.startsWith("image/") && (
                    <PhotoCrop
                      scope="screenplay"
                      container={draft.id}
                      photoId={m.id}
                      filename={m.filename}
                      disabled={locked}
                    />
                  )}
                  <p>Material UID: {m.id}</p>
                  <Button
                    variant="outline"
                    onClick={() => {
                      const popup = window.open("about:blank", "_blank");
                      if (popup) popup.opener = null;
                      void act(async () => {
                        if (!popup)
                          throw new Error(
                            "Allow pop-ups to open the supporting material.",
                          );
                        try {
                          const result = await request<{ url: string }>(
                            `/interviews/screenplays/${id}/materials/${m.id}`,
                          );
                          popup.location.replace(result.url);
                        } catch (error) {
                          popup.close();
                          throw error;
                        }
                      });
                    }}
                  >
                    Open {m.filename}
                  </Button>
                  {m.confirmation?.description && (
                    <p>
                      Interviewee’s description: {m.confirmation.description}
                    </p>
                  )}
                  {m.analysis?.summary && (
                    <details>
                      <summary>Provisional AI interpretation</summary>
                      <p>{m.analysis.summary}</p>
                    </details>
                  )}
                  <label>
                    Notes for {m.filename}
                    <textarea
                      disabled={locked}
                      maxLength={4000}
                      value={m.editor_notes || ""}
                      onChange={(e) =>
                        edit({
                          ...draft,
                          materials: draft.materials.map((item, j) =>
                            j === i
                              ? { ...item, editor_notes: e.target.value }
                              : item,
                          ),
                        })
                      }
                    />
                  </label>
                </div>
              ))}
              <MediaLibrary projectId={draft.project_id} />
              <h3>Attach processed files</h3>
              {media.data
                ?.filter(
                  (a) =>
                    a.status === "ready" &&
                    !draft.materials.some((m) => m.asset_id === a.id),
                )
                .map((a) => (
                  <label key={a.id} className="screenplay-material-choice">
                    <input
                      type="checkbox"
                      disabled={locked}
                      checked={selected.includes(a.id)}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, a.id]
                            : selected.filter((id) => id !== a.id),
                        )
                      }
                    />
                    {a.original_filename}
                  </label>
                ))}
              <Button
                disabled={locked || !selected.length || selected.length > 12}
                onClick={() =>
                  void act(async () => {
                    const value = dirty ? await persist() : draft;
                    update(
                      await request<Screenplay>(
                        `/interviews/screenplays/${id}/materials`,
                        post({ asset_ids: selected, revision: value.revision }),
                      ),
                    );
                    setSelected([]);
                  })
                }
              >
                Attach materials to screenplay
              </Button>
            </details>
            <Button
              disabled={locked || !dirty}
              onClick={() =>
                void act(async () => {
                  await persist();
                  setNotice("Conversation and screenplay edits saved.");
                })
              }
            >
              Save source and edits
            </Button>
          </section>
          <section className="screenplay-panel">
            <h2>2. Draft and review the screenplay</h2>
            <p>
              Each section targets about 60 seconds. Timing is an estimate;
              check the pace with a read-through.
            </p>
            <label>
              Number of 60-second sections
              <input
                type="number"
                min={1}
                max={30}
                value={pages}
                disabled={locked}
                onChange={(e) => setPages(Number(e.target.value))}
              />
            </label>
            <label className="screenplay-material-choice">
              <input
                type="checkbox"
                checked={consent}
                disabled={locked}
                onChange={(e) => setConsent(e.target.checked)}
              />
              Allow Gemini to process the reviewed conversation and material
              descriptions for this screenplay.
            </label>
            <Button
              disabled={locked || !consent || pages < 1 || pages > 30}
              onClick={() => void generate("draft")}
            >
              {draft.sections.length
                ? "Regenerate screenplay draft"
                : "Convert conversation to screenplay draft"}
            </Button>
            {draft.job_kind !== "breakdown" && generationProgress}
            {draft.error && <p role="alert">{draft.error}</p>}
            {draft.draft_stale && (
              <p role="alert">
                The reviewed source has changed. Regenerate the draft before
                preparing or exporting subsections.
              </p>
            )}
          </section>
          {draft.sections.map((page, pi) => (
            <section className="screenplay-panel" key={page.id}>
              <h2>Section {page.position} · approximately 60 seconds</h2>
              <p className="screenplay-uid">Section UID: {page.id}</p>
              <div className="screenplay-paper">
                {page.content.elements.map((element, i) => (
                  <p key={i} className={`screenplay-${element.kind}`}>
                    {element.text}
                  </p>
                ))}
              </div>
              <details>
                <summary>Edit section {page.position}</summary>
                <ContentEditor
                  value={page.content}
                  label={`Section ${page.position}`}
                  materials={draft.materials}
                  disabled={locked}
                  onChange={(value) => pageChange(pi, value)}
                />
                <Button
                  disabled={locked || !dirty}
                  onClick={() =>
                    void act(async () => {
                      await persist();
                      setNotice(`Section ${page.position} saved.`);
                    })
                  }
                >
                  Save section {page.position}
                </Button>
              </details>
              {page.breakdown_stale && (
                <p role="alert">
                  This section changed after its breakdown. Regenerate
                  subsections before exporting.
                </p>
              )}
              {page.subsections.map((sub, si) => (
                <details className="screenplay-subsection" key={sub.id}>
                  <summary>
                    Subsection {page.position}.{sub.position} ·{" "}
                    {sub.start_seconds}–{sub.start_seconds + sub.seconds}s
                  </summary>
                  <p>
                    Interview UID: {draft.interview_uid}
                    <br />
                    Subsection UID: {sub.id}
                  </p>
                  <ContentEditor
                    label={`Subsection ${page.position}.${sub.position}`}
                    value={sub.content}
                    materials={draft.materials}
                    disabled={locked}
                    onChange={(value) => subChange(pi, si, value)}
                  />
                  <Button
                    disabled={locked || !dirty}
                    onClick={() =>
                      void act(async () => {
                        await persist();
                        setNotice(
                          `Subsection ${page.position}.${sub.position} saved.`,
                        );
                      })
                    }
                  >
                    Save subsection {page.position}.{sub.position}
                  </Button>
                </details>
              ))}
            </section>
          ))}
          {!!draft.sections.length && (
            <section className="screenplay-panel">
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "1rem",
                  flexWrap: "wrap",
                  justifyContent: "space-between",
                }}
              >
                <h2>3. Prepare and save video subsections</h2>
                {draft.job_kind === "breakdown" && generationProgress}
              </div>
              <label>
                Subsection duration
                <select
                  disabled={locked}
                  value={seconds}
                  onChange={(e) =>
                    setSeconds(Number(e.target.value) as 10 | 15)
                  }
                >
                  <option value={10}>10 seconds · 6 per section</option>
                  <option value={15}>15 seconds · 4 per section</option>
                </select>
              </label>
              <Button
                disabled={locked || !consent || draft.draft_stale}
                onClick={() => void generate("breakdown")}
              >
                Break into video subsections
              </Button>
              <p>
                Review each subsection above, edit its elements and material
                references, then save. The export retains section IDs,
                subsection IDs and the interview UID.
              </p>
              <Button
                disabled={
                  locked ||
                  !draft.sections.every(
                    (p) => p.subsections.length && !p.breakdown_stale,
                  ) ||
                  draft.draft_stale
                }
                onClick={() =>
                  void act(async () => {
                    if (dirty) await persist();
                    const value = await request<{
                      filename: string;
                      markdown: string;
                    }>(`/interviews/screenplays/${id}/export`, post());
                    const url = URL.createObjectURL(
                      new Blob([value.markdown], {
                        type: "text/markdown;charset=utf-8",
                      }),
                    );
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = value.filename;
                    a.click();
                    URL.revokeObjectURL(url);
                    setNotice(
                      "Screenplay saved to the database and archive. Markdown downloaded.",
                    );
                    await cache.invalidateQueries({
                      queryKey: ["screenplay", id],
                    });
                  })
                }
              >
                Save final screenplay and download Markdown
              </Button>
              {!dirty &&
                !locked &&
                !draft.draft_stale &&
                draft.exports.some(
                  (entry) => entry.revision === draft.revision,
                ) && (
                  <Link
                    className="button button-primary"
                    href={`/cinema-studio?screenplay=${encodeURIComponent(draft.id)}`}
                  >
                    Proceed to Cinema Studio
                  </Link>
                )}
            </section>
          )}
          <Button
            variant="destructive"
            disabled={locked}
            onClick={() => {
              if (
                confirm(
                  "Delete this screenplay and its own exports? The interview and its materials will remain.",
                )
              )
                void act(async () => {
                  await request(`/interviews/screenplays/${id}`, {
                    method: "DELETE",
                  });
                  setId("");
                  setDraft(null);
                  setDirty(false);
                  void cache.invalidateQueries({ queryKey: ["screenplays"] });
                  window.history.replaceState(null, "", "/screenplay-editor");
                });
            }}
          >
            Delete screenplay
          </Button>
        </>
      )}
    </main>
  );
}
