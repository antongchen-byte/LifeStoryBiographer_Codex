"use client";
import { useEffect, useRef, useState } from "react";
import { Project, request } from "../lib/api";
import { Button } from "./ui/button";
export default function BiographyDescription({ project }: { project: Project }) {
  const [text, setText] = useState(project.description ?? "");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [automatic, setAutomatic] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const started = useRef(false);
  const edited = useRef(false);
  const readOnly = project.role === "VIEWER";
  async function generate() {
    setGenerating(true); setError(""); setMessage("");
    try {
      const draft = await request<{description: string}>(`/projects/${project.id}/description-draft`, {method: "POST"});
      if (!edited.current) { setText(draft.description); setAutomatic(true); }
      else setMessage("Your edits were kept. The automatic draft did not replace them.");
    } catch { setError("Unable to generate a description. You can write your own or retry."); }
    finally { setGenerating(false); }
  }
  useEffect(() => {
    if (!started.current && !readOnly && !project.description && new URLSearchParams(window.location.search).get("new") === "1") {
      started.current = true;
      window.history.replaceState(null, "", window.location.pathname);
      void generate();
    }
  }, []);
  return <section className="style-panel">
    <h2>About this biography</h2>
    <p>Describe the story you want to tell, then upload photographs, recordings or documents below.</p>
    {automatic && <p className="style-help">Automatically generated and subjected for changes</p>}
    <label htmlFor="biography-description">Description</label>
    <textarea id="biography-description" rows={5} maxLength={5000} style={{width:"100%"}} value={text} readOnly={readOnly}
      placeholder={generating ? "Preparing a description from your title…" : "Write a description of your biography…"}
      onChange={e => {edited.current = true; setText(e.target.value); setMessage("");}} />
    {generating && <p role="status">Generating a suggested description… You can start writing or upload media below.</p>}
    {!readOnly && <div className="style-actions">
      <Button disabled={saving || generating} onClick={async () => {
        setSaving(true); setError(""); setMessage("");
        try { await request(`/projects/${project.id}`, {method:"PATCH", body:JSON.stringify({description:text})}); setMessage("Description saved. Add media below to bring your story to life."); }
        catch { setError("Unable to save your description. Please try again."); }
        finally { setSaving(false); }
      }}>{saving ? "Saving…" : "Save description"}</Button>
      {!text && !generating && <Button variant="outline" disabled={saving} onClick={() => {edited.current=false; void generate();}}>Suggest from title</Button>}
    </div>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
