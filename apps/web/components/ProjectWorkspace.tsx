"use client";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { ArrowLeft, Settings2, Images, X } from "lucide-react";
import { Project, request } from "../lib/api";
import MediaLibrary from "./MediaLibrary";
import { Button } from "./ui/button";
export default function ProjectWorkspace({ id }: { id: string }) {
  const { data: project, error } = useQuery({
    queryKey: ["project", id],
    queryFn: () => request<Project>(`/projects/${id}`),
  });
  const cache = useQueryClient(),
    dialog = useRef<HTMLDialogElement>(null);
  const [saveError, setSaveError] = useState(""),
    [busy, setBusy] = useState(false);
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setSaveError("");
    const data = new FormData(e.currentTarget);
    try {
      await request(`/projects/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: data.get("title"),
          subject_name: data.get("subject"),
        }),
      });
      void cache.invalidateQueries({ queryKey: ["project", id] });
      dialog.current?.close();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Unable to save");
    } finally {
      setBusy(false);
    }
  }
  if (error)
    return (
      <p role="alert" className="error">
        {error.message}
      </p>
    );
  if (!project) return <p className="muted">Opening biography…</p>;
  return (
    <>
      <Link href="/" className="back-link">
        <ArrowLeft size={15} />
        All biographies
      </Link>
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            THE LIFE OF {project.subject_name.toUpperCase()}
          </span>
          <h1>{project.title || project.subject_name}</h1>
          <p className="muted">
            Collect the moments that make this story uniquely theirs.
          </p>
        </div>
        {project.role !== "VIEWER" && (
          <Button variant="outline" onClick={() => dialog.current?.showModal()}>
            <Settings2 size={16} />
            Project settings
          </Button>
        )}
      </div>
      <div className="workspace-tabs">
        <span>
          <Images size={17} />
          Media Library
        </span>
        <small>{project.role.toLowerCase()} access</small>
      </div>
      <MediaLibrary projectId={id} readOnly={project.role === "VIEWER"} />
      <dialog className="modal" ref={dialog}>
        <div className="modal-heading">
          <h2>Project settings</h2>
          <button
            aria-label="Close settings"
            className="icon-button"
            onClick={() => dialog.current?.close()}
          >
            <X />
          </button>
        </div>
        <form onSubmit={save}>
          <label>
            Subject’s name
            <input
              name="subject"
              defaultValue={project.subject_name}
              required
              maxLength={200}
            />
          </label>
          <label>
            Biography title
            <input
              name="title"
              defaultValue={project.title ?? ""}
              maxLength={250}
            />
          </label>
          {saveError && (
            <p role="alert" className="error">
              {saveError}
            </p>
          )}
          <Button disabled={busy}>Save changes</Button>
        </form>
        {project.role === "OWNER" && (
          <div className="danger-zone">
            <p>Delete this biography after removing its media.</p>
            <Button
              variant="destructive"
              disabled={busy}
              onClick={async () => {
                if (!confirm("Permanently delete this biography?")) return;
                try {
                  await request(`/projects/${id}`, { method: "DELETE" });
                  window.location.assign("/");
                } catch (e) {
                  setSaveError(
                    e instanceof Error ? e.message : "Unable to delete",
                  );
                }
              }}
            >
              Delete biography
            </Button>
          </div>
        )}
      </dialog>
    </>
  );
}
