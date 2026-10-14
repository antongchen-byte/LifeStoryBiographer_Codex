"use client";
import PhotoCrop from "./PhotoCrop";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { request, type MediaAsset } from "../lib/api";
import MediaLibrary from "./MediaLibrary";
import { Button } from "./ui/button";

export type UploadOffer = {
  id: string;
  turn_id: string;
  kind: string;
  status: string;
};
type Material = {
  id: string;
  asset_id: string;
  filename: string;
  mime_type: string;
  url: string;
  sha256: string;
  request_id: string | null;
  analysis_state?: string;
  analysis_error?: string;
  analysis_progress?: number;
  analysis?: { summary?: string; question?: string; uncertainties?: string[] };
  discussion_turn_id?: string;
  confirmation?: { status?: string; description?: string };
};
type Bundle = { root: string; files: { path: string; url: string }[] };
export default function InterviewMaterials({
  sessionId,
  projectId,
  status,
  offers,
  onOpen,
  onClose,
  onSessionChange,
  onDiscussion,
  disabled,
}: {
  sessionId: string;
  projectId: string;
  status: string;
  offers: UploadOffer[];
  onOpen: () => void;
  onClose: () => void;
  onSessionChange: (value: unknown) => void;
  onDiscussion: (value: unknown) => void;
  disabled: boolean;
}) {
  const cache = useQueryClient();
  const dialog = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false),
    [offerId, setOfferId] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]),
    [working, setWorking] = useState(false),
    [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const shown = useRef(new Set<string>());
  const callbacks = useRef({ onOpen, onClose, onDiscussion });
  callbacks.current = { onOpen, onClose, onDiscussion };
  const materials = useQuery({
    queryKey: ["interview-materials", sessionId],
    queryFn: () =>
      request<Material[]>(`/interviews/sessions/${sessionId}/materials`),
    refetchInterval: status === "approved" ? false : 2500,
  });
  const discussing = useRef(false);
  useEffect(() => {
    if (status !== "active" || open || disabled || discussing.current) return;
    if (
      materials.data?.some(
        (m) =>
          m.analysis_state === "ready" &&
          m.discussion_turn_id &&
          !m.confirmation?.status,
      )
    )
      return;
    if (
      !materials.data?.some(
        (m) => m.analysis_state === "ready" && !m.discussion_turn_id,
      )
    )
      return;
    discussing.current = true;
    callbacks.current.onOpen();
    void request(`/interviews/sessions/${sessionId}/materials/discuss`, {
      method: "POST",
      body: "{}",
    })
      .then(async (value) => {
        onSessionChange(value);
        await cache.invalidateQueries({
          queryKey: ["interview-materials", sessionId],
        });
        callbacks.current.onDiscussion(value);
      })
      .catch((e) =>
        setNotice(
          e instanceof Error ? e.message : "Unable to discuss materials",
        ),
      )
      .finally(() => {
        discussing.current = false;
      });
  }, [
    materials.data,
    status,
    open,
    disabled,
    sessionId,
    cache,
    onSessionChange,
  ]);

  async function analysisAction(id: string, action: "analyze" | "skip") {
    setWorking(true);
    try {
      await request(
        `/interviews/sessions/${sessionId}/materials/${id}/${action}`,
        { method: "POST", body: "{}" },
      );
      await cache.invalidateQueries({
        queryKey: ["interview-materials", sessionId],
      });
      await cache.invalidateQueries({ queryKey: ["interview", sessionId] });
      if (action === "skip") callbacks.current.onClose();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "Unable to update analysis");
    } finally {
      setWorking(false);
    }
  }
  const media = useQuery({
    queryKey: ["media", projectId],
    queryFn: () => request<MediaAsset[]>(`/projects/${projectId}/media`),
    enabled: open,
    refetchInterval: open ? 2000 : false,
  });
  const bundle = useQuery({
    queryKey: ["interview-bundle", sessionId, status],
    queryFn: () => request<Bundle>(`/interviews/sessions/${sessionId}/bundle`),
    enabled: status === "approved",
    retry: false,
  });
  useEffect(() => {
    const pending = offers.find(
      (item) => item.status === "pending" && !shown.current.has(item.id),
    );
    if (!pending || open || status === "approved") return;
    shown.current.add(pending.id);
    setOfferId(pending.id);
    setSelected([]);
    setError("");
    callbacks.current.onOpen();
    setOpen(true);
  }, [offers, open, status]);
  useEffect(() => {
    if (open && !dialog.current?.open) dialog.current?.showModal();
    if (!open && dialog.current?.open) dialog.current.close();
  }, [open]);
  async function closeOffer() {
    if (working) return;
    setWorking(true);
    setError("");
    try {
      if (offerId)
        onSessionChange(
          await request(
            `/interviews/sessions/${sessionId}/upload-requests/${offerId}/decline`,
            { method: "POST", body: "{}" },
          ),
        );
      setOpen(false);
      setOfferId(null);
      callbacks.current.onClose();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Unable to close upload request",
      );
    } finally {
      setWorking(false);
    }
  }
  async function attach() {
    setWorking(true);
    setError("");
    try {
      const result = await request(
        `/interviews/sessions/${sessionId}/materials`,
        {
          method: "POST",
          body: JSON.stringify({ asset_ids: selected, request_id: offerId }),
        },
      );
      onSessionChange(result);
      await cache.invalidateQueries({
        queryKey: ["interview-materials", sessionId],
      });
      setOpen(false);
      setOfferId(null);
      setNotice(
        "Materials attached. Analyzing their contents; the interviewer will ask you to confirm the interpretation and share your own description.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to attach materials");
    } finally {
      setWorking(false);
    }
  }
  async function saveFolder() {
    const picker = (
      window as Window & {
        showDirectoryPicker?: (options: {
          mode: "readwrite";
        }) => Promise<FileSystemDirectoryHandle>;
      }
    ).showDirectoryPicker;
    if (!picker) {
      setNotice(
        "Use Chrome or Edge to save the full folder, or download the individual files below.",
      );
      return;
    }
    try {
      const chosen = await picker({ mode: "readwrite" });
      setWorking(true);
      setNotice("");
      const result = await request<Bundle>(
        `/interviews/sessions/${sessionId}/bundle`,
      );
      const root = await chosen.getDirectoryHandle(`interview-${sessionId}`, {
        create: true,
      });
      for (const file of result.files) {
        const parts = file.path.split("/");
        if (parts.some((part) => !part || part === "." || part === ".."))
          throw new Error("Invalid archive path");
        let folder = root;
        for (const part of parts.slice(0, -1))
          folder = await folder.getDirectoryHandle(part, { create: true });
        const response = await fetch(file.url);
        if (!response.ok || !response.body)
          throw new Error(
            "File download failed. Retry to finish saving the folder.",
          );
        const handle = await folder.getFileHandle(parts.at(-1)!, {
          create: true,
        });
        const writer = await handle.createWritable();
        await response.body.pipeTo(writer);
      }
      setNotice(
        "Approved script and materials saved together in the selected folder.",
      );
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError"))
        setNotice(e instanceof Error ? e.message : "Folder save failed");
    } finally {
      setWorking(false);
    }
  }
  return (
    <section className="interview-materials" aria-label="Interview materials">
      {materials.data?.map((m) => (
        <div className="interview-material-analysis" key={m.id}>
          <strong>{m.filename}</strong>
          {m.mime_type?.startsWith("image/") && (
            <PhotoCrop
              scope="interview"
              container={sessionId}
              photoId={m.id}
              filename={m.filename}
              disabled={disabled}
            />
          )}
          <p role="status">
            {["pending", "dispatched", "running"].includes(
              m.analysis_state || "",
            )
              ? `Analyzing material… ${m.analysis_progress || 0} sections completed. You may wait or continue describing it yourself.`
              : `Analysis: ${m.analysis_state || "not started"}`}
          </p>
          {["pending", "dispatched", "running"].includes(
            m.analysis_state || "",
          ) && <progress aria-label={`Analyzing ${m.filename}`} />}
          {m.analysis_error && <p role="alert">{m.analysis_error}</p>}
          {m.analysis?.summary && (
            <details>
              <summary>AI interpretation — please confirm or correct</summary>
              <p>{m.analysis.summary}</p>
              <p>{m.analysis.question}</p>
            </details>
          )}
          {m.confirmation?.status && (
            <p>
              Your response: {m.confirmation.status}.{" "}
              {m.confirmation.description}
            </p>
          )}
          {status !== "approved" &&
            ["failed", "not_started", "skipped"].includes(
              m.analysis_state || "",
            ) && (
              <Button
                disabled={working || disabled}
                onClick={() => void analysisAction(m.id, "analyze")}
              >
                Analyze {m.filename}
              </Button>
            )}
          {status !== "approved" &&
            ["pending", "dispatched", "running", "failed"].includes(
              m.analysis_state || "",
            ) && (
              <Button
                variant="outline"
                disabled={working || disabled}
                onClick={() => void analysisAction(m.id, "skip")}
              >
                Skip analysis and continue
              </Button>
            )}
        </div>
      ))}
      <details>
        <summary>Supporting materials ({materials.data?.length || 0})</summary>
        <p>
          These files belong to this interview, separately from interviewer
          style references.
        </p>
        {materials.error && <p role="alert">{materials.error.message}</p>}
        {materials.data?.map((m) => (
          <p key={m.id}>
            <a href={m.url} target="_blank" rel="noreferrer">
              {m.filename}
            </a>
          </p>
        ))}
        {status === "approved" && bundle.data && (
          <>
            <p>
              The approved script and materials share this archive folder:{" "}
              <code>{bundle.data.root}</code>
            </p>
            <Button disabled={working} onClick={() => void saveFolder()}>
              Save script and materials to local folder
            </Button>
            <ul>
              {bundle.data.files.map((file) => (
                <li key={file.path}>
                  <a href={file.url} target="_blank" rel="noreferrer">
                    {file.path}
                  </a>
                </li>
              ))}
            </ul>
          </>
        )}
      </details>
      {status !== "approved" && (
        <Button
          variant="outline"
          disabled={disabled || working}
          onClick={() => {
            setOfferId(offers.find((o) => o.status === "pending")?.id || null);
            setSelected([]);
            setError("");
            callbacks.current.onOpen();
            setOpen(true);
          }}
        >
          Add interview materials
        </Button>
      )}
      {notice && <p role="status">{notice}</p>}
      <dialog
        ref={dialog}
        className="interview-upload-dialog"
        aria-labelledby="interview-upload-title"
        onCancel={(event) => {
          event.preventDefault();
          void closeOffer();
        }}
      >
        <h2 id="interview-upload-title">
          Would you like to upload supporting materials?
        </h2>
        <p>
          You mentioned sharing a picture, article or other material. Upload it
          now, choose a processed file below, or decline and continue the
          conversation.
        </p>
        <Button
          variant="outline"
          disabled={working}
          onClick={() => void closeOffer()}
        >
          No thanks, continue interview
        </Button>
        {error && <p role="alert">{error}</p>}
        <MediaLibrary projectId={projectId} />
        <h3>Select processed files to attach</h3>
        <p>
          Wait for processing to finish. Select the files you want saved with
          this interview.
        </p>
        {media.data
          ?.filter(
            (a) =>
              a.status === "ready" &&
              !materials.data?.some((m) => m.asset_id === a.id),
          )
          .map((a) => (
            <label className="interview-check" key={a.id}>
              <input
                type="checkbox"
                checked={selected.includes(a.id)}
                disabled={working}
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
          disabled={working || !selected.length || selected.length > 12}
          onClick={() => void attach()}
        >
          Attach selected materials and continue
        </Button>
        <Button
          variant="outline"
          disabled={working}
          onClick={() => void closeOffer()}
        >
          Close and continue without uploading
        </Button>
      </dialog>
    </section>
  );
}
