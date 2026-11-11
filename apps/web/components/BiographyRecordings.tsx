"use client";
import {useState} from "react";
import Link from "next/link";
import {useQuery, useQueryClient} from "@tanstack/react-query";
import {request} from "../lib/api";
import {Workspace, type Detail} from "./StyleLab";
import {Button} from "./ui/button";
export default function BiographyRecordings({projectId}: {projectId:string}) {
  const cache=useQueryClient();
  const [selected,setSelected]=useState("");
  const [busy,setBusy]=useState(false), [error,setError]=useState(""), [notice,setNotice]=useState("");
  const profiles=useQuery({queryKey:["style-profiles"],queryFn:()=>request<{id:string;name:string;project_id:string}[]>("/profiles")});
  const collections=profiles.data?.filter(p=>p.project_id===projectId) ?? [];
  const profileId=selected || collections[0]?.id;
  const detail=useQuery({queryKey:["style",profileId],queryFn:()=>request<Detail>(`/profiles/${profileId}`),enabled:!!profileId,refetchInterval:4000});
  async function action(work:()=>Promise<unknown>,message="Saved") {
    setBusy(true);setError("");setNotice("");
    try {await work();await Promise.all(["style","style-turns","style-profiles","media","interview-sources"].map(key=>cache.invalidateQueries({queryKey:[key]})));setNotice(message);}
    catch(e){setError(e instanceof Error?e.message:"Please try again");}
    finally{setBusy(false);}
  }
  return <section id="recording-scripts">
    <h2>Recording scripts</h2>
    <p>Convert uploaded audio and video, review the transcript, then approve and save it to your script library. Saved scripts can be selected in <Link href="/style-lab">Style Lab</Link>.</p>
    {(error || profiles.error || detail.error) && <p role="alert">{error || profiles.error?.message || detail.error?.message}</p>}
    {notice && <p role="status">{notice}</p>}
    {profiles.isPending && <p>Loading recording scripts…</p>}
    {!profiles.isPending && !profiles.error && !collections.length && <Button disabled={busy} onClick={()=>void action(async()=>{
      const p=await request<Detail>(`/projects/${projectId}/transcription-profile`,{method:"POST"});setSelected(p.id);
    },"Ready to create transcripts from your uploaded recordings.")}>Prepare uploaded recordings for transcription</Button>}
    {collections.length>1 && <label>Recording collection<select value={profileId} onChange={e=>setSelected(e.target.value)}>{collections.map(p=><option value={p.id} key={p.id}>{p.name}</option>)}</select></label>}
    {detail.data && <Workspace key={detail.data.id} profile={detail.data} action={action} busy={busy} recordingsOnly />}
  </section>;
}
