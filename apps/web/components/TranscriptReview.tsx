"use client";
import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "../lib/api";
import { Button } from "./ui/button";
import {
  Transcript,
  SpeakerRoles,
  RecordingPlayer,
  type Detail,
  type Turn,
} from "./StyleLab";

type Archive = {
  id: string;
  revision: number;
  sha256: string;
  saved_at: string | null;
  folder_label: string | null;
};
type Export = Archive & { filename: string; json: string; text: string };
type Directory = {
  name: string;
  getFileHandle(
    name: string,
    options: { create: boolean },
  ): Promise<{
    createWritable(): Promise<{
      write(data: string): Promise<void>;
      close(): Promise<void>;
      abort(): Promise<void>;
    }>;
    getFile(): Promise<File>;
  }>;
};
type PickerWindow = Window & {
  showDirectoryPicker?: (options: { mode: "readwrite" }) => Promise<Directory>;
};
type Match = {
  archive_id: string;
  source_id: string;
  revision: number;
  filename: string;
  speaker: string;
  role: string;
  start_ms: number;
  end_ms: number;
  text: string;
  turn_id: string;
};
const json = (body: unknown) => ({
  method: "POST",
  body: JSON.stringify(body),
});
async function digest(value: string) {
  return Array.from(
    new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)),
    ),
  )
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export default function TranscriptReview({
  profileId,
  sourceId,
}: {
  profileId: string;
  sourceId: string;
}) {
  const base = `/profiles/${profileId}`;
  const cache = useQueryClient();
  const [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(""),
    [error, setError] = useState("");
  const [selected, setSelected] = useState<Turn[]>([]);
  const [query, setQuery] = useState(""),
    [search, setSearch] = useState(""),
    [offset, setOffset] = useState(0);
  const [preview, setPreview] = useState<Export | null>(null);
  const profile = useQuery({
    queryKey: ["style", profileId],
    queryFn: () => request<Detail>(base),
    refetchInterval: 4000,
  });
  const archives = useQuery({
    queryKey: ["script-archives", sourceId],
    queryFn: () => request<Archive[]>(`${base}/sources/${sourceId}/archives`),
  });
  const matches = useQuery({
    queryKey: ["script-memory", profileId, search, offset],
    queryFn: () =>
      request<{ items: Match[]; has_more: boolean }>(
        `${base}/memory?q=${encodeURIComponent(search)}&offset=${offset}`,
      ),
    enabled: !!search,
  });
  const source = profile.data?.sources.find((s) => s.id === sourceId);
  const processing = profile.data?.jobs.some((j) =>
    ["pending", "dispatched", "running", "stopping"].includes(j.state),
  );
  async function action(work: () => Promise<unknown>, message = "Saved") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await work();
      await Promise.all([
        cache.invalidateQueries({ queryKey: ["style"] }),
        cache.invalidateQueries({ queryKey: ["style-turns"] }),
        cache.invalidateQueries({ queryKey: ["script-archives"] }),
        cache.invalidateQueries({ queryKey: ["script-memory"] }),
      ]);
      setNotice(message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save");
    } finally {
      await cache.invalidateQueries({ queryKey: ["script-archives"] });
      setBusy(false);
    }
  }
  function save(archiveId?: string) {
    const picker = (window as PickerWindow).showDirectoryPicker;
    if (!picker) {
      setError(
        "Folder saving requires desktop Chrome or Edge. Open this page there to choose a local folder.",
      );
      return;
    }
    // Open synchronously within the click gesture, before any network request.
    const selection = picker.call(window, { mode: "readwrite" });
    void action(async () => {
      let directory: Directory;
      try {
        directory = await selection;
      } catch (e) {
        if (e instanceof DOMException && e.name === "AbortError")
          throw new Error(
            "Folder selection cancelled. No files were saved or indexed.",
          );
        throw e;
      }
      const archive = archiveId
        ? await request<Export>(`${base}/archives/${archiveId}`)
        : await request<Export>(
            `${base}/sources/${sourceId}/archives`,
            json({ revision: source!.revision }),
          );
      if ((await digest(archive.json)) !== archive.sha256)
        throw new Error("Archive integrity check failed. Nothing was indexed.");
      for (const [extension, content] of [
        ["json", archive.json],
        ["txt", archive.text],
      ]) {
        const handle = await directory.getFileHandle(
          `${archive.filename}.${extension}`,
          { create: true },
        );
        const writer = await handle.createWritable();
        try {
          await writer.write(content);
          await writer.close();
        } catch (e) {
          await writer.abort().catch(() => {});
          throw e;
        }
        if ((await (await handle.getFile()).text()) !== content)
          throw new Error(
            "Local file verification failed. Nothing was indexed; retry saving this version.",
          );
      }
      await request(
        `${base}/archives/${archive.id}/saved`,
        json({ sha256: archive.sha256, folder_label: directory.name }),
      );
    }, "Script saved as TXT and JSON in your selected folder and added to searchable memory.");
  }
  if (profile.error)
    return (
      <div className="page">
        <p role="alert">{profile.error.message}</p>
        <Link href="/style-lab">Back to Style Lab</Link>
      </div>
    );
  if (!profile.data) return <div className="page">Loading script…</div>;
  if (!source)
    return (
      <div className="page">
        Recording not found. <Link href="/style-lab">Back to Style Lab</Link>
      </div>
    );
  return (
    <div className="page style-lab">
      <Link href="/style-lab">← Back to Style Lab</Link>
      <header className="page-heading">
        <div>
          <p className="eyebrow">SCRIPT REVIEW</p>
          <h1>{source.filename}</h1>
          <p>
            Review the words, speaker roles, and timing. Approve the script,
            then save a permanent copy in a folder you choose.
          </p>
        </div>
      </header>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="style-notice" role="status">
          {notice}
        </p>
      )}
      <SpeakerRoles
        base={base}
        source={source}
        action={action}
        blocked={busy || !!processing}
      />
      <section className="style-panel">
        <h2>Review and save</h2>
        <Button
          variant="destructive"
          disabled={busy || !!processing}
          onClick={() => {
            if (
              !window.confirm(
                `Delete the script and processing history for "${source.filename}"? This removes approved script versions, searchable memory, related patterns and published style versions, and profile analysis history. The uploaded recording is kept. Exported files in your local folders are not deleted. This cannot be undone.`,
              )
            )
              return;
            void action(async () => {
              await request(`${base}/sources/${sourceId}/script`, {
                method: "DELETE",
              });
              setPreview(null);
              setSelected([]);
            }, "Script and processing history deleted. The recording is retained; return to Style Lab to create a new transcript.");
          }}
        >
          Delete script
        </Button>

        <p>
          Revision {source.revision} · {source.turn_count} turns ·{" "}
          {source.reviewed ? "Reviewed" : "Needs review"}
        </p>
        <RecordingPlayer
          projectId={profile.data.project_id}
          assetId={source.asset_id}
          mime={source.mime_type}
          action={action}
        />
        <p className="style-help">
          Saving creates a timestamped TXT script and a structured JSON copy.
          Memory is indexed after both files are written and verified. Folder
          selection is available in desktop Chrome and Edge.
        </p>
        <Button
          disabled={busy || processing || !source.turn_count}
          onClick={() => save()}
        >
          Approve & save to local folder
        </Button>
        {processing && (
          <p>Wait for processing to finish before approving or editing.</p>
        )}
      </section>
      <section className="style-panel">
        <h2>Script</h2>
        <Transcript
          key={`${source.id}-${source.turn_count === 0 ? "empty" : "populated"}`}
          base={base}
          source={source}
          action={action}
          showSelection={false}
          showSpeakerPanel={false}
          blocked={busy || !!processing}
          selected={selected}
          setSelected={setSelected}
        />
      </section>
      <section className="style-panel">
        <h2>Approved versions</h2>
        <p>
          Edits create a new revision. Previous approved copies remain
          unchanged.
        </p>
        {archives.error && <p role="alert">{archives.error.message}</p>}
        {archives.data?.length === 0 && <p>No approved versions yet.</p>}
        {archives.data?.map((a) => (
          <div className="style-panel" key={a.id}>
            <strong>Revision {a.revision}</strong>
            <p>
              {a.saved_at
                ? `Saved and indexed · ${a.folder_label} · ${new Date(a.saved_at).toLocaleString()}`
                : "Approved · local save not confirmed · not indexed"}
            </p>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() =>
                void action(
                  async () =>
                    setPreview(
                      await request<Export>(`${base}/archives/${a.id}`),
                    ),
                  "Approved version opened",
                )
              }
            >
              View saved script
            </Button>{" "}
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => save(a.id)}
            >
              {a.saved_at ? "Save another copy" : "Retry local save"}
            </Button>
          </div>
        ))}
        {preview && (
          <div>
            <h3>Approved revision {preview.revision}</h3>
            <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
              {preview.text}
            </pre>
            <Button variant="outline" onClick={() => setPreview(null)}>
              Close saved script
            </Button>
          </div>
        )}
      </section>
      <section className="style-panel">
        <h2>Search conversation memory</h2>
        <p>
          Search the latest locally saved script from each recording in this
          profile. Results retain their speaker, time, and approved version.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setOffset(0);
            setSearch(query.trim());
          }}
        >
          <label>
            Words to find
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={300}
              required
            />
          </label>
          <Button disabled={!query.trim()}>Search saved scripts</Button>
        </form>
        {matches.error && <p role="alert">{matches.error.message}</p>}
        {matches.isFetching && <p>Searching…</p>}
        {matches.data?.items.length === 0 && <p>No matching saved scripts.</p>}
        {matches.data?.items.map((m) => (
          <article className="style-panel" key={`${m.archive_id}-${m.turn_id}`}>
            <strong>
              {m.filename} · revision {m.revision}
            </strong>
            <p>
              {m.speaker} ({m.role}) · {(m.start_ms / 1000).toFixed(1)}–
              {(m.end_ms / 1000).toFixed(1)}s
            </p>
            <p>{m.text}</p>
            <Button
              variant="outline"
              onClick={() =>
                void action(
                  async () =>
                    setPreview(
                      await request<Export>(`${base}/archives/${m.archive_id}`),
                    ),
                  "Source version opened above",
                )
              }
            >
              View source version
            </Button>
          </article>
        ))}
        {offset > 0 && (
          <Button variant="outline" onClick={() => setOffset(offset - 30)}>
            Previous results
          </Button>
        )}
        {matches.data?.has_more && (
          <Button variant="outline" onClick={() => setOffset(offset + 30)}>
            More results
          </Button>
        )}
      </section>
    </div>
  );
}
