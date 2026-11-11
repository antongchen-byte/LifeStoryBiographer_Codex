"use client";
import Link from "next/link";
import {useEffect} from "react";
import {useQuery} from "@tanstack/react-query";
import {request} from "../lib/api";
const modules:Record<string,string>={biography:"My Biographies",style:"Style Lab",interview:"Interview Studio",screenplay:"Screenplay Editor",cinema:"Cinema Studio"};
export default function ProductionReviews({projectId,library=false}:{projectId:string;library?:boolean}){
 const reviews=useQuery({queryKey:['production-reviews',projectId],queryFn:()=>request<{id:string;title:string;module:string;editor_name:string;version_number:number;created_at:string}[]>(`/production/projects/${projectId}/reviews`),refetchInterval:15000});
 useEffect(()=>{const refresh=()=>{void reviews.refetch();};window.addEventListener('production-review-shared',refresh);return()=>window.removeEventListener('production-review-shared',refresh);},[projectId]);
 if(reviews.error)return <p role="alert">Unable to load editor versions: {reviews.error.message}</p>;
 if(!library){
  if(!reviews.data?.length)return null;
  return <aside className="editor-versions-entry" data-editor-copy-exclude aria-label="Editor copies are separate"><strong>Updates from your Editor</strong><p>{reviews.data.length} separate read-only {reviews.data.length===1?'copy':'copies'} available. You are viewing your working biography here.</p><Link href={`/projects/${projectId}/editor-versions`}>Review editor versions →</Link></aside>;
 }
 return <section data-editor-copy-exclude><Link href={`/projects/${projectId}`}>← Back to your working biography</Link><h1>Versions from your Editor</h1><p>This area contains only copies shared by an editor. Your working biography and its content are on a separate page.</p>{reviews.isPending&&<p>Loading editor versions…</p>}{reviews.data?.length===0&&<p>No editor versions have been shared yet.</p>}{reviews.data?.map(r=><article className="editor-version-card" key={r.id}><strong className="editor-version-badge">EDITOR COPY · READ ONLY</strong><h2><Link href={`/projects/${projectId}/editor-versions/${r.id}`}>Editor-{r.version_number} — {modules[r.module]||r.module}</Link></h2><p>Shared by <strong>{r.editor_name}</strong> · {new Date(r.created_at).toLocaleString()}</p><p>{r.title}</p></article>)}</section>;
}
