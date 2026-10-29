"use client";
import PhotoCrop from "./PhotoCrop";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type ChangeEvent } from "react";
import {
  UploadCloud,
  Image as ImageIcon,
  Film,
  Music,
  FileText,
  X,
  Download,
  RotateCcw,
  Trash2,
  Search,
  Check,
  Pause,
} from "lucide-react";
import { MediaAsset, bytes, request } from "../lib/api";
import { Button } from "./ui/button";
const MIME: Record<string, string> = {
  gif: "image/gif",
  tif: "image/tiff",
  tiff: "image/tiff",
  bmp: "image/bmp",
  avif: "image/avif",
  heif: "image/heif",
  flac: "audio/flac",
  ogg: "audio/ogg",
  opus: "audio/ogg",
  aiff: "audio/aiff",
  aif: "audio/aiff",
  avi: "video/x-msvideo",
  mkv: "video/x-matroska",
  "3gp": "video/3gpp",
  wmv: "video/x-ms-wmv",
  csv: "text/csv",
  html: "text/html",
  htm: "text/html",
  doc: "application/msword",
  rtf: "application/rtf",
  odt: "application/vnd.oasis.opendocument.text",
  ppt: "application/vnd.ms-powerpoint",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  odp: "application/vnd.oasis.opendocument.presentation",
  xls: "application/vnd.ms-excel",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  ods: "application/vnd.oasis.opendocument.spreadsheet",

  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  heic: "image/heic",
  mp4: "video/mp4",
  mov: "video/quicktime",
  mpeg: "video/mpeg",
  mpg: "video/mpeg",
  m4v: "video/x-m4v",
  webm: "video/webm",
  mp3: "audio/mpeg",
  wav: "audio/wav",
  m4a: "audio/mp4",
  aac: "audio/aac",
  txt: "text/plain",
  md: "text/markdown",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  pdf: "application/pdf",
};
const ACCEPT = Object.keys(MIME)
  .map((s) => `.${s}`)
  .join(",");
type Part = { part_number: number; etag: string };
type Started = {
  asset_id: string;
  status: string;
  part_size: number;
  part_urls: string[];
  uploaded_parts: Part[];
};
function icon(mime: string) {
  return mime.startsWith("image")
    ? ImageIcon
    : mime.startsWith("video")
      ? Film
      : mime.startsWith("audio")
        ? Music
        : FileText;
}
function AssetCard({
  asset,
  onOpen,
}: {
  asset: MediaAsset;
  onOpen: () => void;
}) {
  const Icon = icon(asset.mime_type);
  const thumbnail = useQuery({
    queryKey: ["thumbnail", asset.id],
    queryFn: () =>
      request<{ url: string }>(
        `/projects/${asset.project_id}/media/${asset.id}/download?kind=thumbnail`,
      ),
    enabled: asset.status === "ready" && asset.has_thumbnail,
    staleTime: 240000,
  });
  return (
    <button className="asset-card" onClick={onOpen}>
      <div className={`asset-visual ${asset.mime_type.split("/")[0]}`}>
        {thumbnail.data ? (
          <img src={thumbnail.data.url} alt={asset.original_filename} />
        ) : (
          <Icon size={34} strokeWidth={1.3} />
        )}
        <span className={`asset-status status-${asset.status}`}>
          {asset.status === "ready" ? (
            <>
              <Check size={12} />
              Ready
            </>
          ) : asset.status === "uploaded" ? (
            "Queued"
          ) : (
            asset.status
          )}
        </span>
      </div>
      <div className="asset-info">
        <h3 title={asset.original_filename}>{asset.original_filename}</h3>
        <p>
          {asset.mime_type.split("/")[0]}
          <span>·</span>
          {bytes(asset.size_bytes)}
        </p>
      </div>
    </button>
  );
}
export default function MediaLibrary({
  projectId,
  readOnly = false,
  templatesOnly = false,
}: {
  projectId: string;
  readOnly?: boolean;
  templatesOnly?: boolean;
}) {
  const cache = useQueryClient(),
    picker = useRef<HTMLInputElement>(null),
    controller = useRef<AbortController | null>(null),
    busy = useRef(false);
  const [uploading, setUploading] = useState(false),
    [progress, setProgress] = useState(0),
    [message, setMessage] = useState("");
  const [error, setError] = useState(""),
    [consent, setConsent] = useState(false),
    [dragging, setDragging] = useState(false),
    [filter, setFilter] = useState("all"),
    [search, setSearch] = useState("");
  const [selected, setSelected] = useState<MediaAsset | null>(null),
    [description, setDescription] = useState(""),
    [actionBusy, setActionBusy] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const media = useQuery({
    queryKey: ["media", projectId],
    queryFn: () => request<MediaAsset[]>(`/projects/${projectId}/media`),
    refetchInterval: 5000,
  });
  const assets = media.data ?? [];
  const current = assets.find((a) => a.id === selected?.id) ?? selected;
  const preview = useQuery({
    queryKey: ["preview", current?.id, current?.status],
    queryFn: () =>
      request<{ url: string }>(
        `/projects/${projectId}/media/${current!.id}/download?kind=${current!.has_proxy ? "proxy" : current!.mime_type === "image/heic" ? "thumbnail" : "original"}`,
      ),
    enabled: !!current && current.status === "ready",
    staleTime: 240000,
  });
  function refresh() {
    void cache.invalidateQueries({ queryKey: ["media", projectId] });
    void cache.invalidateQueries({ queryKey: ["projects"] });
  }
  async function upload(files: FileList | null) {
    if (!files || busy.current || readOnly) return;
    if (!consent) {
      setError(
        "Confirm you have permission to use these files before uploading.",
      );
      return;
    }
    busy.current = true;
    setUploading(true);
    setError("");
    controller.current = new AbortController();
    const signal = controller.current.signal;
    let skipped = 0;
    try {
      for (const file of Array.from(files)) {
        if (signal.aborted) throw new DOMException("Paused", "AbortError");
        if (templatesOnly && !/\.(md|txt|pdf|docx)$/i.test(file.name)) throw new Error("Choose a Markdown, TXT, PDF or Word .docx template.");
        if (templatesOnly && file.size > 20 * 1024 * 1024) throw new Error("Templates must be at most 20 MiB.");
        if (!file.size) throw new Error("Files must be nonempty.");
        const mime = MIME[file.name.split(".").pop()?.toLowerCase() ?? ""];
        if (!mime) throw new Error(`Unsupported format: ${file.name}`);
        if (
          !mime.startsWith("audio/") &&
          !mime.startsWith("video/") &&
          file.size > 2 * 1024 ** 3
        )
          throw new Error("Images and documents must be no larger than 2 GiB.");
        setMessage(`Uploading ${file.name}`);
        setProgress(0);
        const storageKey = `upload:${projectId}:${file.name}:${file.size}:${file.lastModified}`;
        const saved = JSON.parse(
          localStorage.getItem(storageKey) ?? "null",
        ) as { key: string; parts: Part[] } | null;
        const key = saved?.key ?? crypto.randomUUID();
        setMessage(`Checking existing materials for ${file.name}`);
        const uploadData = {
          filename: file.name,
          mime_type: mime,
          size_bytes: file.size,
          idempotency_key: key,
          ownership_declared: true,
        };
        const matches = await request<
          { project_title: string; filename: string; status: string }[]
        >(`/projects/${projectId}/media/duplicates`, {
          method: "POST",
          body: JSON.stringify(uploadData),
          signal,
        });
        if (signal.aborted) throw new DOMException("Paused", "AbortError");
        const allowDuplicate =
          matches.length > 0 &&
          window.confirm(
            `Possible duplicate: ${file.name}\n\nYou already uploaded material with the same filename and size:\n${matches.map((m) => `• ${m.project_title} — ${m.filename} (${m.status})`).join("\n")}\n\nPlease use the existing material unless another copy is really necessary. Filename and size are a reminder, not proof of identical contents.\n\nOK: upload another copy. Cancel: skip this file.`,
          );
        if (matches.length && !allowDuplicate) {
          skipped++;
          continue;
        }
        setMessage(`Uploading ${file.name}`);
        localStorage.setItem(
          storageKey,
          JSON.stringify({ key, parts: saved?.parts ?? [] }),
        );
        const started = await request<Started>(
          `/projects/${projectId}/media/uploads`,
          {
            method: "POST",
            body: JSON.stringify({
              ...uploadData,
              allow_duplicate: allowDuplicate,
            }),
            signal,
          },
        );
        if (started.status !== "uploading") {
          localStorage.removeItem(storageKey);
          continue;
        }
        const parts = new Map<number, Part>(
          started.uploaded_parts.map((p) => [p.part_number, p]),
        );
        for (let i = 0; i < started.part_urls.length; i++) {
          if (!parts.has(i + 1)) {
            let response: Response | undefined;
            for (let attempt = 0; attempt < 3; attempt++) {
              try {
                response = await fetch(started.part_urls[i], {
                  method: "PUT",
                  body: file.slice(
                    i * started.part_size,
                    (i + 1) * started.part_size,
                  ),
                  signal,
                });
                if (response.ok) break;
              } catch (e) {
                if (signal.aborted || attempt === 2) throw e;
              }
              if (attempt === 2)
                throw new Error(
                  "An upload part failed. Reselect this file to resume.",
                );
            }
            const etag = response?.headers.get("etag");
            if (!etag)
              throw new Error(
                "The storage service did not confirm this upload part.",
              );
            parts.set(i + 1, { part_number: i + 1, etag });
            localStorage.setItem(
              storageKey,
              JSON.stringify({ key, parts: Array.from(parts.values()) }),
            );
          }
          setProgress(Math.round(((i + 1) / started.part_urls.length) * 100));
        }
        await request(
          `/projects/${projectId}/media/${started.asset_id}/complete`,
          {
            method: "POST",
            body: JSON.stringify({
              parts: Array.from(parts.values()).sort(
                (a, b) => a.part_number - b.part_number,
              ),
            }),
            signal,
          },
        );
        localStorage.removeItem(storageKey);
        refresh();
      }
      setMessage(
        skipped === files.length
          ? "Duplicate files skipped. No new copies were uploaded."
          : `Upload complete. Your files are being processed.${skipped ? ` Skipped ${skipped} possible duplicate(s).` : ""}`,
      );
    } catch (e) {
      setError(
        signal.aborted
          ? "Upload paused. Reselect the same file to resume."
          : e instanceof Error
            ? e.message
            : "Upload failed. Reselect the file to resume.",
      );
    } finally {
      busy.current = false;
      setUploading(false);
      refresh();
      if (picker.current) picker.current.value = "";
    }
  }
  async function action(operation: () => Promise<unknown>, close = false) {
    setActionBusy(true);
    setError("");
    try {
      await operation();
      refresh();
      if (close) {
        dialog.current?.close();
        setSelected(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Please retry.");
    } finally {
      setActionBusy(false);
    }
  }
  function open(asset: MediaAsset) {
    setSelected(asset);
    setDescription(asset.description ?? "");
    dialog.current?.showModal();
  }
  const filtered = assets.filter(
    (a) =>
      (filter === "all" ||
        a.mime_type.startsWith(filter) ||
        (filter === "application" && a.mime_type.startsWith("text/"))) &&
      a.original_filename.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <section>
      {!readOnly && (
        <div
          className={`upload-zone ${dragging ? "dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            void upload(e.dataTransfer.files);
          }}
        >
          <span className="upload-symbol">
            <UploadCloud size={29} strokeWidth={1.5} />
          </span>
          <h3>{templatesOnly ? "Upload your own templates" : "Bring your memories together"}</h3>
          <p>{templatesOnly ? "Choose reference documents from your computer, or drop them here." : "Drop photographs, videos, recordings, or documents here."}</p>
          <Button
            variant="outline"
            disabled={uploading || !consent}
            onClick={() => picker.current?.click()}
          >
            {templatesOnly ? "Upload reference templates" : "Choose files"}
          </Button>
          <input
            className="sr-only"
            aria-label="Upload files"
            type="file"
            ref={picker}
            multiple
            accept={templatesOnly ? ".md,.txt,.pdf,.docx" : ACCEPT}
            onChange={(e: ChangeEvent<HTMLInputElement>) =>
              void upload(e.target.files)
            }
          />
          <small>
            {templatesOnly ? "Markdown (.md), TXT, PDF or Word (.docx) · up to 20 MiB per template" : "JPG, PNG, HEIC · MP4, MOV · MP3, WAV · PDF, DOCX and more · no recording file-size cap"}
          </small>
          <label className="consent">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            I own these files or have permission to use them.
          </label>
        </div>
      )}
      {uploading && (
        <div className="upload-progress">
          <div>
            <span>{message}</span>
            <span>{progress}%</span>
          </div>
          <progress value={progress} max={100} />
          <Button variant="ghost" onClick={() => controller.current?.abort()}>
            <Pause size={14} />
            Pause upload
          </Button>
        </div>
      )}
      {!uploading && message && !error && (
        <p className="success" role="status">
          {message}
        </p>
      )}
      {(error || media.error) && (
        <p className="error" role="alert">
          {error || media.error?.message}
        </p>
      )}
      <div className="library-toolbar">
        <div className="filter-tabs" aria-label="Filter media">
          {["all", "image", "video", "audio", "application"].map((value, i) => (
            <button
              key={value}
              className={filter === value ? "selected" : ""}
              onClick={() => setFilter(value)}
            >
              {["All memories", "Photos", "Videos", "Audio", "Documents"][i]}
              {value === "all" && <span>{assets.length}</span>}
            </button>
          ))}
        </div>
        <div className="search-wrap">
          <Search size={15} />
          <input
            aria-label="Search media"
            placeholder="Find a memory…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>
      {media.isPending ? (
        <div className="empty-state">Loading memories…</div>
      ) : filtered.length ? (
        <div className="media-grid">
          {filtered.map((a) => (
            <AssetCard key={a.id} asset={a} onOpen={() => open(a)} />
          ))}
        </div>
      ) : (
        <div className="empty-state compact">
          <ImageIcon size={30} strokeWidth={1} />
          <h3>
            {assets.length
              ? "No matching memories"
              : "A home for your memories"}
          </h3>
          <p>
            {assets.length
              ? "Try a different filter or search."
              : "Your uploaded files will appear here, ready to explore."}
          </p>
        </div>
      )}
      <dialog
        className="modal media-modal"
        ref={dialog}
        onClose={(event) => {
          if (event.target === event.currentTarget) setSelected(null);
        }}
      >
        {current && (
          <>
            <div className="modal-heading">
              <h2>{current.original_filename}</h2>
              <button
                className="icon-button"
                aria-label="Close media"
                onClick={() => dialog.current?.close()}
              >
                <X />
              </button>
            </div>
            <div className="media-preview">
              {preview.data && current.mime_type.startsWith("image/") ? (
                <img alt={current.original_filename} src={preview.data.url} />
              ) : preview.data && current.mime_type.startsWith("video/") ? (
                <video controls src={preview.data.url} />
              ) : preview.data && current.mime_type.startsWith("audio/") ? (
                <audio controls src={preview.data.url} />
              ) : (
                <FileText size={52} strokeWidth={1} />
              )}
            </div>
            <p className="muted">
              {bytes(current.size_bytes)} · {current.status}
              {current.width ? ` · ${current.width} × ${current.height}` : ""}
              {current.duration_ms
                ? ` · ${(current.duration_ms / 1000).toFixed(1)} seconds`
                : ""}
            </p>
            {current.error && <p className="error">{current.error}</p>}
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <label>
              The story behind this memory
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                disabled={readOnly}
                placeholder="Who is in this photo? When and where was it taken?"
                maxLength={5000}
              />
            </label>
            {!readOnly &&
              current.status === "ready" &&
              current.mime_type.startsWith("image/") && (
                <PhotoCrop
                  key={current.id}
                  scope="media"
                  container={projectId}
                  photoId={current.id}
                  filename={current.original_filename}
                />
              )}
            <div className="modal-actions">
              {!readOnly && (
                <Button
                  disabled={actionBusy}
                  onClick={() =>
                    void action(() =>
                      request(`/projects/${projectId}/media/${current.id}`, {
                        method: "PATCH",
                        body: JSON.stringify({ description }),
                      }),
                    )
                  }
                >
                  Save note
                </Button>
              )}
              {current.status === "ready" && (
                <Button
                  variant="outline"
                  onClick={() =>
                    void action(async () => {
                      const data = await request<{ url: string }>(
                        `/projects/${projectId}/media/${current.id}/download`,
                      );
                      window.location.assign(data.url);
                    })
                  }
                >
                  <Download size={15} />
                  Original
                </Button>
              )}
              {!readOnly && current.status === "failed" && (
                <Button
                  variant="outline"
                  disabled={actionBusy}
                  onClick={() =>
                    void action(
                      () =>
                        request(
                          `/projects/${projectId}/media/${current.id}/retry`,
                          { method: "POST" },
                        ),
                      true,
                    )
                  }
                >
                  <RotateCcw size={15} />
                  Retry
                </Button>
              )}
              {!readOnly &&
                !["processing", "uploaded"].includes(current.status) && (
                  <Button
                    variant="ghost"
                    disabled={actionBusy}
                    aria-label="Delete media"
                    onClick={() => {
                      if (
                        confirm(
                          "Permanently delete this file and its processed versions?",
                        )
                      )
                        void action(
                          () =>
                            request(
                              `/projects/${projectId}/media/${current.id}`,
                              { method: "DELETE" },
                            ),
                          true,
                        );
                    }}
                  >
                    <Trash2 size={17} />
                  </Button>
                )}
            </div>
            {current.checksum_sha256 && (
              <details className="provenance">
                <summary>Original file verification</summary>
                <p>SHA-256 checksum</p>
                <code>{current.checksum_sha256}</code>
              </details>
            )}
          </>
        )}
      </dialog>
    </section>
  );
}
