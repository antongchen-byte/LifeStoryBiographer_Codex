"use client";
import PhotoCrop from "./PhotoCrop";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { request } from "../lib/api";
import { Button } from "./ui/button";

type Prompt = {
  material_variants?: Record<string, string>;
  prompt: string;
  continuity: string;
  material_ids: string[];
  previous_id: string | null;
};
type Job = {
  id: string;
  state: string;
  kind: string;
  request: Prompt;
  previewed: boolean;
  approved: boolean;
  frame_ready: boolean;
  duration: number | null;
  error: string | null;
  preview_url: string | null;
  download_url: string | null;
  recoverable: boolean;
};
type Unit = {
  id: string;
  position: number;
  section_position: number;
  seconds: number;
  prompt: string;
  content: {
    material_ids: string[];
    elements: { kind: string; text: string }[];
  };
  stale: boolean;
  clip: Job | null;
};
type Production = {
  id: string;
  screenplay_id: string;
  title: string;
  revision: number;
  interview_uid: string;
  all_approved: boolean;
  units: Unit[];
  renders: Job[];
  materials: { id: string; filename: string; mime_type: string }[];
};
const ACTIVE = [
  "pending",
  "dispatched",
  "running",
  "submitting",
  "polling",
  "processing",
];
const post = (body: unknown = {}) => ({
  method: "POST",
  body: JSON.stringify(body),
});
const label = (unit: Unit) => `${unit.section_position}.${unit.position}`;

function VideoPreview({
  url,
  label,
  onEnded,
}: {
  url: string;
  label: string;
  onEnded?: () => void;
}) {
  // Renewing signed links during status polling must not restart playback.
  const [source, setSource] = useState(url);
  const [failed, setFailed] = useState(false);
  return (
    <>
      <video
        controls
        preload="metadata"
        src={source}
        aria-label={label}
        onEnded={onEnded}
        onError={() => setFailed(true)}
      />
      {failed && (
        <Button
          variant="outline"
          onClick={() => {
            setSource(url);
            setFailed(false);
          }}
        >
          Reload video preview
        </Button>
      )}
    </>
  );
}

function ClipEditor({
  unit,
  previous,
  production,
  consent,
  busy,
  action,
}: {
  unit: Unit;
  previous?: Unit;
  production: Production;
  consent: boolean;
  busy: boolean;
  action: (path: string, body?: unknown) => Promise<void>;
}) {
  const clip = unit.clip;
  const [prompt, setPrompt] = useState(clip?.request.prompt ?? unit.prompt);
  const [continuity, setContinuity] = useState(
    clip?.request.continuity ??
      unit.content.elements
        .filter((e) => e.kind === "scene" || e.kind === "character")
        .map((e) => e.text)
        .join("\n"),
  );
  const [bridge, setBridge] = useState(!!clip?.request.previous_id);
  const photos = production.materials.filter(
    (m) =>
      unit.content.material_ids.includes(m.id) &&
      m.mime_type.startsWith("image/"),
  );
  const [selected, setSelected] = useState(
    clip?.request.material_ids ?? photos.slice(0, 3).map((m) => m.id),
  );
  const [variants, setVariants] = useState<Record<string, string>>(
    clip?.request.material_variants ?? {},
  );
  const [useCropped, setUseCropped] = useState<string[]>(
    Object.keys(clip?.request.material_variants ?? {}),
  );
  const [previewed, setPreviewed] = useState(clip?.previewed ?? false);
  const [unsatisfied, setUnsatisfied] = useState(false);
  const [reviewError, setReviewError] = useState("");
  const promptBox = useRef<HTMLTextAreaElement>(null);
  const generating = !!clip && ACTIVE.includes(clip.state);
  const canBridge =
    previous?.clip?.state === "ready" &&
    previous.clip.frame_ready &&
    !previous.stale;
  async function generate(same = false) {
    const prior = same && clip ? clip.request : null;
    await action(`/subsections/${unit.id}/generate`, {
      prompt: prior?.prompt ?? prompt,
      continuity: prior?.continuity ?? continuity,
      material_ids: (prior ? !!prior.previous_id : bridge)
        ? []
        : (prior?.material_ids ?? selected),
      material_variants: (prior ? !!prior.previous_id : bridge)
        ? {}
        : prior
          ? (prior.material_variants ?? {})
          : Object.fromEntries(
              Object.entries(variants).filter(
                ([mid]) => selected.includes(mid) && useCropped.includes(mid),
              ),
            ),
      previous_frame: prior ? !!prior.previous_id : bridge,
      consent,
      expected_clip_id: clip?.id ?? null,
    });
  }
  return (
    <article className="cinema-clip panel">
      <div>
        <h3>Subsection {label(unit)}</h3>
        <p className="muted">
          Screenplay: {unit.seconds}s · Veo clip:{" "}
          {clip?.duration?.toFixed(1) ?? "8"}s
        </p>
        <label>
          Video prompt for subsection {label(unit)}
          <textarea
            ref={promptBox}
            rows={9}
            maxLength={12000}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={generating}
          />
        </label>
        <label>
          Consistent character and environment descriptions
          <textarea
            rows={3}
            maxLength={4000}
            value={
              bridge
                ? (previous?.clip?.request.continuity ?? continuity)
                : continuity
            }
            disabled={bridge || generating}
            onChange={(e) => setContinuity(e.target.value)}
          />
        </label>
        {previous && (
          <label className="cinema-choice">
            <input
              type="checkbox"
              checked={bridge}
              disabled={generating}
              onChange={(e) => setBridge(e.target.checked)}
            />
            Start from last frame of previous clip
          </label>
        )}
        {bridge && (
          <p className="muted">
            Character and environment descriptions are inherited unchanged from
            the previous clip.{" "}
            {canBridge
              ? "Its final frame will be sent as the starting image."
              : !previous?.clip
                ? "Generate the previous clip first."
                : previous.stale
                  ? "Regenerate the previous clip: its continuity is out of date."
                  : previous.clip.state !== "ready"
                    ? "Wait for the previous clip to finish successfully."
                    : "The previous clip’s final frame is not available yet."}
          </p>
        )}
        {!consent && (
          <p role="status">
            Enable the Veo consent checkbox at the top of this page to generate
            clips.
          </p>
        )}
        {bridge && (
          <p>
            Using the previous clip’s final frame. Reference photos are not sent
            in this mode. Uncheck the frame option to use photos instead.
          </p>
        )}
        {photos.length > 0 && (
          <fieldset disabled={bridge}>
            <legend>Use photos selected in Screenplay Editor (up to 3)</legend>
            {photos.map((photo) => (
              <div key={photo.id}>
                <label className="cinema-choice">
                  <input
                    type="checkbox"
                    checked={selected.includes(photo.id)}
                    disabled={
                      generating ||
                      (!selected.includes(photo.id) && selected.length >= 3)
                    }
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [...selected, photo.id]
                          : selected.filter((id) => id !== photo.id),
                      )
                    }
                  />
                  {photo.filename}
                </label>
                <PhotoCrop
                  scope="cinema"
                  container={production.id}
                  photoId={photo.id}
                  filename={photo.filename}
                  disabled={busy || generating}
                  onSaved={(asset) => {
                    setVariants((current) => ({
                      ...current,
                      [photo.id]: asset.id,
                    }));
                    setUseCropped((current) =>
                      current.includes(photo.id)
                        ? current
                        : [...current, photo.id],
                    );
                  }}
                />
                <label className="cinema-choice">
                  <input
                    type="checkbox"
                    checked={
                      !!variants[photo.id] && useCropped.includes(photo.id)
                    }
                    disabled={busy || generating || !variants[photo.id]}
                    onChange={(event) =>
                      setUseCropped((current) =>
                        event.target.checked
                          ? [...current, photo.id]
                          : current.filter((id) => id !== photo.id),
                      )
                    }
                  />
                  Use edited image (cropped / text removed) for {photo.filename}
                </label>
                <p className="muted">
                  {bridge
                    ? "Not sent: previous-frame mode is selected."
                    : !selected.includes(photo.id)
                      ? "This photo is not included in the next generation."
                      : variants[photo.id] && useCropped.includes(photo.id)
                        ? "Next generation will use the edited image (cropped / text removed)."
                        : "Next generation will use the original image."}
                  {!variants[photo.id] &&
                    " Create a cropped or text-removed copy above to enable this option."}
                </p>
                {clip?.request.material_ids.includes(photo.id) && (
                  <p className="muted">
                    Current clip used:{" "}
                    {clip.request.material_variants?.[photo.id]
                      ? "edited image (cropped / text removed)"
                      : "original image"}
                    .
                  </p>
                )}
              </div>
            ))}
          </fieldset>
        )}
        <Button
          disabled={
            busy ||
            generating ||
            !consent ||
            !prompt.trim() ||
            (bridge && !canBridge)
          }
          onClick={() => void generate()}
        >
          {clip ? "Generate revised clip" : "Generate video clip"}
        </Button>
      </div>
      <div>
        {generating && (
          <div role="status">
            <p>
              {clip.state === "polling"
                ? "Veo is generating your clip…"
                : `Video job: ${clip.state}`}
            </p>
            <progress aria-label={`Generation progress ${label(unit)}`} />
            <p className="muted">
              You can leave this page and return. Veo does not report a
              completion percentage.
            </p>
          </div>
        )}
        {clip?.error && <p role="alert">{clip.error}</p>}
        {clip?.recoverable && (
          <Button
            disabled={busy}
            onClick={() => void action(`/clips/${clip.id}/resume`)}
          >
            Resume generation without a new Veo request
          </Button>
        )}
        {unit.stale && (
          <p role="alert">
            The previous clip changed. Regenerate this clip from its new final
            frame before approval.
          </p>
        )}
        {clip?.state === "ready" && clip.preview_url && (
          <>
            {reviewError && <p role="alert">{reviewError}</p>}
            <VideoPreview
              key={clip.id}
              url={clip.preview_url}
              label={`Preview subsection ${label(unit)}`}
              onEnded={() => {
                void request(
                  `/cinema/${production.id}/clips/${clip.id}/previewed`,
                  post(),
                )
                  .then(() => {
                    setPreviewed(true);
                    setReviewError("");
                  })
                  .catch((e) => setReviewError(e.message));
              }}
            />
            <a className="button button-secondary" href={clip.download_url!}>
              Download clip {label(unit)}
            </a>
            {!previewed && (
              <p>Play the preview through to the end to review this clip.</p>
            )}
            {previewed && (
              <div>
                <p>Are you satisfied with this clip?</p>
                <Button
                  disabled={busy || unit.stale || clip.approved}
                  onClick={() =>
                    void action(`/clips/${clip.id}/review`, { approved: true })
                  }
                >
                  {clip.approved ? "Approved" : "Yes, satisfied"}
                </Button>
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    setUnsatisfied(true);
                    void action(`/clips/${clip.id}/review`, {
                      approved: false,
                    });
                  }}
                >
                  No, revise this clip
                </Button>
              </div>
            )}
            {unsatisfied && (
              <div>
                <p>Edit the prompt, or try again with the same prompt?</p>
                <Button
                  variant="outline"
                  onClick={() => promptBox.current?.focus()}
                >
                  Edit prompt
                </Button>
                <Button
                  disabled={
                    busy ||
                    !consent ||
                    generating ||
                    (!!clip.request.previous_id && !canBridge)
                  }
                  onClick={() => void generate(true)}
                >
                  Regenerate with the same prompt
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </article>
  );
}

type Directory = {
  getDirectoryHandle(
    name: string,
    options: { create: boolean },
  ): Promise<Directory>;
  getFileHandle(
    name: string,
    options: { create: boolean },
  ): Promise<{
    createWritable(): Promise<{
      write(blob: Blob): Promise<void>;
      close(): Promise<void>;
    }>;
  }>;
};

export default function CinemaStudio({
  screenplayId,
}: {
  screenplayId?: string;
}) {
  const [selected, setSelected] = useState(screenplayId ?? "");
  const [production, setProduction] = useState<Production | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [consent, setConsent] = useState(false);
  const [skipStitch, setSkipStitch] = useState(false);
  const screenplays = useQuery({
    queryKey: ["screenplays"],
    queryFn: () =>
      request<
        { id: string; title: string; revision: number; interview_uid: string }[]
      >("/interviews/screenplays"),
  });
  useEffect(() => {
    if (!selected) {
      setProduction(null);
      return;
    }
    let cancelled = false;
    setProduction(null);
    setError("");
    setSkipStitch(false);
    setNotice("");
    request<Production>(
      `/cinema/screenplays/${encodeURIComponent(selected)}`,
      post(),
    )
      .then((p) => {
        if (!cancelled) setProduction(p);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    window.history.replaceState(
      null,
      "",
      `/cinema-studio?screenplay=${encodeURIComponent(selected)}`,
    );
    return () => {
      cancelled = true;
    };
  }, [selected]);
  const current = useQuery({
    queryKey: ["cinema", production?.id],
    enabled: !!production,
    queryFn: () => request<Production>(`/cinema/${production!.id}`),
    refetchInterval: 5000,
  });
  useEffect(() => {
    if (current.data && current.data.id === production?.id)
      setProduction(current.data);
  }, [current.data, production?.id]);
  async function action(path: string, body: unknown = {}) {
    if (!production) return;
    setBusy(true);
    setError("");
    try {
      const value = await request<Production>(
        `/cinema/${production.id}${path}`,
        post(body),
      );
      setProduction(value);
      await current.refetch();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function downloadScreenplay() {
    if (!production) return;
    setError("");
    try {
      const file = await request<{ filename: string; markdown: string }>(
        `/cinema/${production.id}/screenplay`,
      );
      const url = URL.createObjectURL(
        new Blob([file.markdown], { type: "text/markdown;charset=utf-8" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = file.filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function localFolder() {
    if (!production) return;
    const picker = (
      window as unknown as { showDirectoryPicker?: () => Promise<Directory> }
    ).showDirectoryPicker;
    if (!picker) {
      setNotice(
        "Use Download all clips (ZIP), then extract it into your chosen folder.",
      );
      return;
    }
    setBusy(true);
    setError("");
    try {
      const directory = await picker.call(window);
      const folder = await directory.getDirectoryHandle(
        `interview-${production.interview_uid}-${production.id}`,
        { create: true },
      );
      for (const unit of production.units) {
        const response = await fetch(unit.clip!.download_url!);
        if (!response.ok)
          throw new Error("A clip download failed. Retry saving the folder.");
        const file = await folder.getFileHandle(
          `${label(unit)}-${unit.clip!.id}.mp4`,
          { create: true },
        );
        const writer = await file.createWritable();
        await writer.write(await response.blob());
        await writer.close();
      }
      const manifest = await folder.getFileHandle("manifest.json", {
        create: true,
      });
      const writer = await manifest.createWritable();
      await writer.write(
        new Blob([
          JSON.stringify(
            {
              interview_uid: production.interview_uid,
              screenplay_id: production.screenplay_id,
              revision: production.revision,
              clips: production.units.map((u) => ({
                subsection_id: u.id,
                clip_id: u.clip!.id,
                prompt: u.clip!.request,
              })),
            },
            null,
            2,
          ),
        ]),
      );
      await writer.close();
      setNotice("Approved clips saved to your selected folder.");
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const bundle = production?.renders.findLast((j) => j.kind === "bundle");
  const film = production?.renders.findLast((j) => j.kind === "stitch");
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">YOUR BIOGRAPHY STUDIO</span>
          <h1>Cinema Studio</h1>
          <p className="muted">
            Generate, review, and assemble your video clips.
          </p>
        </div>
      </div>
      <label className="cinema-screenplay-select">
        Choose your screenplay
        <select
          value={selected}
          disabled={busy}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">Select a saved screenplay</option>
          {screenplays.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title} · revision {s.revision} · {s.id.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      {screenplays.error && <p role="alert">{screenplays.error.message}</p>}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {selected && !production && !error && (
        <p role="status">Loading saved screenplay…</p>
      )}
      {production && (
        <>
          <h2>{production.title}</h2>
          <Button variant="outline" onClick={() => void downloadScreenplay()}>
            Download saved screenplay Markdown
          </Button>
          <p className="muted">
            Interview UID: {production.interview_uid} · Saved revision{" "}
            {production.revision}
          </p>
          <p>
            Model: veo-3.1-generate-preview. Each generation produces an
            8-second, 720p clip with audio. Your screenplay’s planned 10- or
            15-second timing remains unchanged.
          </p>
          <label className="cinema-choice">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            I agree to send these prompts and selected photos to Veo. Each new
            generation may incur API charges.
          </label>
          {production.units.map((unit, index) => (
            <ClipEditor
              key={`${production.id}-${unit.id}-${unit.clip?.id ?? "new"}`}
              unit={unit}
              previous={production.units[index - 1]}
              production={production}
              consent={consent}
              busy={busy}
              action={action}
            />
          ))}
          {production.all_approved && (
            <section className="panel">
              <h2>All clips approved</h2>
              <p>
                Save the approved collection and download it to your computer.
              </p>
              <Button
                disabled={busy || (!!bundle && ACTIVE.includes(bundle.state))}
                onClick={() => void action("/renders/bundle")}
              >
                Save approved clips to database and archive
              </Button>
              {bundle && ACTIVE.includes(bundle.state) && (
                <p role="status">Preparing your download…</p>
              )}
              {bundle?.error && <p role="alert">{bundle.error}</p>}
              {bundle?.state === "ready" && (
                <>
                  <a
                    className="button button-primary"
                    href={bundle.download_url!}
                  >
                    Download all clips (ZIP)
                  </a>
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => void localFolder()}
                  >
                    Save clips to a local folder
                  </Button>
                  {!skipStitch && (
                    <div>
                      <p>
                        Would you like to stitch all approved clips in
                        sequential order?
                      </p>
                      <Button
                        disabled={
                          busy || (!!film && ACTIVE.includes(film.state))
                        }
                        onClick={() => void action("/renders/stitch")}
                      >
                        Yes, stitch clips
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => setSkipStitch(true)}
                      >
                        Not now
                      </Button>
                    </div>
                  )}
                  {skipStitch && (
                    <Button
                      variant="outline"
                      onClick={() => setSkipStitch(false)}
                    >
                      Show stitching options
                    </Button>
                  )}
                  {film && ACTIVE.includes(film.state) && (
                    <p role="status">Stitching clips in screenplay order…</p>
                  )}
                  {film?.error && <p role="alert">{film.error}</p>}
                  {film?.state === "ready" && (
                    <>
                      <VideoPreview
                        key={film.id}
                        url={film.preview_url!}
                        label="Preview assembled film"
                      />
                      <a
                        className="button button-primary"
                        href={film.download_url!}
                      >
                        Download stitched film
                      </a>
                    </>
                  )}
                </>
              )}
            </section>
          )}
        </>
      )}
      <Link
        className="button button-secondary"
        href={
          selected
            ? `/screenplay-editor?screenplay=${encodeURIComponent(selected)}`
            : "/screenplay-editor"
        }
      >
        Back to Screenplay Editor
      </Link>
    </>
  );
}
