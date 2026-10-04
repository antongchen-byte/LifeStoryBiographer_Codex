"use client";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import {
  ArrowRight,
  Plus,
  BookOpen,
  Image,
  Sparkles,
  X,
  FolderOpen,
} from "lucide-react";
import { Project, request } from "../lib/api";
import { Button } from "../components/ui/button";
export default function Dashboard() {
  const {
    data: projects = [],
    isPending,
    error,
  } = useQuery({
    queryKey: ["projects"],
    queryFn: () => request<Project[]>("/projects"),
  });
  const client = useQueryClient(),
    dialog = useRef<HTMLDialogElement>(null);
  const [search, setSearch] = useState("");
  const create = useMutation({
    mutationFn: (body: { subject_name: string; title: string }) =>
      request<Project>("/projects", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["projects"] });
      dialog.current?.close();
    },
  });
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    create.mutate({
      subject_name: String(data.get("subject")),
      title: String(data.get("title")),
    });
  }
  const filtered = projects.filter((p) =>
    `${p.title} ${p.subject_name}`.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">THE STORIES THAT MAKE US</span>
          <h1>
            My biographies<span className="heading-dot">.</span>
          </h1>
          <p className="muted">A collection of lives, waiting to be told.</p>
        </div>
        <Button
          onClick={() => {
            create.reset();
            dialog.current?.showModal();
          }}
        >
          <Plus size={17} />
          New biography
        </Button>
      </div>
      <section className="hero">
        <div>
          <span className="tiny-label">FROM A MEMORY TO A MOVIE</span>
          <h2>
            Every life has a story.
            <br />
            Let’s bring one to life.
          </h2>
          <p>
            Gather the photographs, voices, and little moments.
            <br />
            Build something that will be treasured for generations.
          </p>
          <Button variant="outline" onClick={() => dialog.current?.showModal()}>
            Start a biography <ArrowRight size={16} />
          </Button>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="paper paper-back"></div>
          <div className="paper paper-front">
            <div className="paper-landscape">
              <span />
              <i />
            </div>
            <div className="paper-caption">a life, well told.</div>
          </div>
          <span className="hero-star">✳</span>
        </div>
      </section>
      <div className="section-heading">
        <h2>
          Your collection <span className="count">{projects.length}</span>
        </h2>
        <input
          className="search"
          aria-label="Search biographies"
          placeholder="Search biographies…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      {error && (
        <p className="error" role="alert">
          {error.message}
        </p>
      )}
      {isPending ? (
        <div className="empty-state">Loading your biographies…</div>
      ) : filtered.length ? (
        <div className="project-grid">
          {filtered.map((p, i) => (
            <Link
              href={`/projects/${p.id}`}
              className="project-card"
              key={p.id}
            >
              <div className={`project-cover cover-${i % 3}`}>
                <BookOpen size={42} strokeWidth={1} />
                <span>
                  {p.subject_name
                    .split(" ")
                    .map((n) => n[0])
                    .slice(0, 2)
                    .join("")}
                </span>
                <small className="status-pill">
                  {p.status.replaceAll("_", " ")}
                </small>
              </div>
              <div className="project-info">
                <small className="tiny-label">A LIFE STORY</small>
                <h3>{p.title || `The life of ${p.subject_name}`}</h3>
                <p>{p.subject_name}</p>
                <div className="project-meta">
                  <span>
                    <Image size={14} />
                    {p.media_count}{" "}
                    {p.media_count === 1 ? "memory" : "memories"}
                  </span>
                  <ArrowRight size={18} />
                </div>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <span className="empty-icon">
            <FolderOpen size={28} />
          </span>
          <h3>
            {search
              ? "No matching biographies"
              : "Your first story starts here"}
          </h3>
          <p>
            {search
              ? "Try another name or title."
              : "Create a biography and give your memories a home."}
          </p>
          {!search && (
            <Button
              variant="outline"
              onClick={() => dialog.current?.showModal()}
            >
              <Plus size={16} />
              Create a biography
            </Button>
          )}
        </div>
      )}
      <div className="gentle-note">
        <Sparkles size={18} />
        <p>
          You’re the curator. Your sources and editorial choices stay at the
          heart of every story.
        </p>
      </div>
      <dialog ref={dialog} className="modal">
        <div className="modal-heading">
          <h2>A new biography</h2>
          <button
            className="icon-button"
            aria-label="Close"
            onClick={() => dialog.current?.close()}
          >
            <X />
          </button>
        </div>
        <p className="muted">Whose story would you like to preserve?</p>
        <form onSubmit={submit}>
          <label>
            Subject’s name
            <input
              name="subject"
              placeholder="e.g. Elena Martin"
              required
              maxLength={200}
            />
          </label>
          <label>
            Biography title <span className="muted">(optional)</span>
            <input
              name="title"
              placeholder="e.g. A life of small adventures"
              maxLength={250}
            />
          </label>
          {create.error && (
            <p role="alert" className="error">
              {create.error.message}
            </p>
          )}
          <Button disabled={create.isPending} className="full-width">
            {create.isPending ? "Creating…" : "Create biography"}
            <ArrowRight size={16} />
          </Button>
        </form>
      </dialog>
    </>
  );
}
