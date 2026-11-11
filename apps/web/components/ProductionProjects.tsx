"use client";
import {useState} from "react";
import {useQuery} from "@tanstack/react-query";
import {request} from "../lib/api";
import {Button} from "./ui/button";
export default function ProductionProjects(){
 const [search,setSearch]=useState(""),[q,setQ]=useState(""),[error,setError]=useState(""),[busy,setBusy]=useState(false);
 const capability=useQuery({queryKey:["production-me"],queryFn:()=>request<{production_editor:boolean;actor_id:string}>("/production/me")});
 const projects=useQuery({queryKey:["production-projects",q],enabled:capability.data?.production_editor===true,queryFn:()=>request<{id:string;title:string;owner_name:string;owner_email:string;readiness:string}[]>(`/production/projects?q=${encodeURIComponent(q)}`)});
 if(capability.isPending)return <p>Checking access…</p>;
 if(!capability.data?.production_editor)return <p role="alert">Production Editor access is required.</p>;
 return <><h1>Production projects</h1><p>Choose an owner and project to continue their production.</p><form onSubmit={e=>{e.preventDefault();setQ(search);}}><label>Search owner or project<input value={search} onChange={e=>setSearch(e.target.value)} /></label><Button>Search</Button></form>
 {(error || projects.error) && <p role="alert">{error || projects.error?.message}</p>}
 {projects.isPending && <p role="status">Loading production projects…</p>}
 {projects.data?.length===0 && <p>{q ? "No projects match this search. Clear the search to see all projects." : "No biographies have been created in this installation yet."}</p>}
 {projects.data && <p>{projects.data.length} projects available</p>}
 {projects.data?.map(p=><section className="style-panel" key={p.id}><h2>{p.title}</h2><p>{p.owner_name} · {p.owner_email}</p><p>{p.readiness}</p><Button disabled={busy} onClick={async()=>{setBusy(true);setError("");const previous=sessionStorage.getItem("production-project");sessionStorage.setItem("production-project",JSON.stringify({...p,actor_id:capability.data?.actor_id}));try{const opened=await request(`/production/projects/${p.id}/open`,{method:"POST"});sessionStorage.setItem("production-project",JSON.stringify(opened));sessionStorage.removeItem("working-project");window.location.assign(`/projects/${p.id}`);}catch(e){if(previous)sessionStorage.setItem("production-project",previous);else sessionStorage.removeItem("production-project");setError(e instanceof Error?e.message:"Unable to open project");setBusy(false);}}}>Open project</Button></section>)}
 </>;
}
