"use client";
import {useState} from "react";
import ProductionReleases from "./ProductionReleases";
import Link from "next/link";
import {useQuery} from "@tanstack/react-query";
import {request} from "../lib/api";
import {Button} from "./ui/button";
export default function ProductionReview({projectId,reviewId}:{projectId:string;reviewId:string}){
 const result=useQuery({queryKey:['production-review',projectId,reviewId],queryFn:()=>request<{id:string;title:string;content:string;created_at:string;editor_name:string;version_number:number;module:string;can_create_project:boolean}>(`/production/projects/${projectId}/reviews/${reviewId}`)});
 const [busy,setBusy]=useState(false),[error,setError]=useState("");
 if(result.error)return <p role="alert">{result.error.message}</p>;
 if(!result.data)return <p>Loading editor version…</p>;
 const version=result.data;
 return <article><Link href={`/projects/${projectId}/editor-versions`}>← All editor versions</Link><div className="editor-versions-entry"><strong className="editor-version-badge">EDITOR COPY · READ ONLY</strong><h1>Editor-{version.version_number}</h1><p>{version.title}</p><p>Shared by <strong>{version.editor_name}</strong> · {new Date(version.created_at).toLocaleString()}</p><Link href={`/projects/${projectId}`}>Return to your working biography →</Link></div>{version.can_create_project ? <Button disabled={busy} onClick={async()=>{setBusy(true);setError('');try{const opened=await request(`/production/projects/${projectId}/reviews/${reviewId}/open-project`,{method:'POST'});sessionStorage.removeItem('production-project');sessionStorage.setItem('working-project',JSON.stringify(opened));window.location.assign(`/projects/${(opened as {id:string}).id}`);}catch(e){setError(e instanceof Error?e.message:'Unable to create project');setBusy(false);}}}>{busy?'Copying project and materials…':'Open as a separate editable project'}</Button> : <p role="status">This older version contains page text only. Ask the editor to share a new complete project version to open it across all modules.</p>}{error&&<p role="alert">{error}</p>}<p>This separate page copy does not replace your working version. Uploaded files and video previews remain in the project’s original material library.</p><Button onClick={()=>{const url=URL.createObjectURL(new Blob([`# ${version.title}\n\nSource: Editor-${version.version_number} (read-only)\nShared by: ${version.editor_name}\nShared: ${new Date(version.created_at).toISOString()}\nVersion ID: ${version.id}\n\nThis is a separate editor copy. The owner’s working version is unchanged.\n\n---\n\n${version.content}`],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`Editor-version-${version.id}.md`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}}>Download Markdown copy</Button><ProductionReleases projectId={projectId} reviewId={reviewId}/><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{version.content}</pre></article>;
}
