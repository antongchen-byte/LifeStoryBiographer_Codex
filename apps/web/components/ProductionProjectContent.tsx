"use client";
import Link from "next/link";
import {useQuery} from "@tanstack/react-query";
import {request} from "../lib/api";
export default function ProductionProjectContent({projectId}:{projectId:string}) {
 const sessions=useQuery({queryKey:["production-project-interviews",projectId],queryFn:()=>request<{id:string;project_id:string;title:string;status:string}[]>("/interviews/sessions")});
 const configs=useQuery({queryKey:["production-project-configs",projectId],queryFn:()=>request<{id:string;project_id:string;name:string}[]>("/interviews/configs")});
 return <section className="style-panel" aria-label="Existing project work"><h2>Existing project work</h2><p>Open saved interviews to review the conversation and its uploaded materials. Original uploads are in the Media Library below.</p>
 {(sessions.isPending || configs.isPending) && <p>Loading saved work…</p>}
 {(sessions.error || configs.error) && <p role="alert">{sessions.error?.message || configs.error?.message}</p>}
 <h3>Saved interviewer configurations</h3>
 {configs.data?.filter(c=>c.project_id===projectId).map(c=><p key={c.id}><Link href={`/style-lab?config=${c.id}`}>{c.name}</Link></p>)}
 {configs.data?.length===0 && <p>No saved interviewer configurations.</p>}
 <h3>Interviews and supporting materials</h3>
 {sessions.data?.filter(s=>s.project_id===projectId).map(s=><p key={s.id}><Link href={`/interview-studio/${s.id}/review`}>{s.title}</Link> · {s.status}</p>)}
 {sessions.data?.length===0 && <p>No saved interviews.</p>}
 </section>;
}
