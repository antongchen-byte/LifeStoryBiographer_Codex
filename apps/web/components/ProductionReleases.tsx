"use client";
import Link from "next/link";
import {useQuery} from "@tanstack/react-query";
import {request} from "../lib/api";
export default function ProductionReleases({projectId,reviewId}:{projectId:string;reviewId?:string}){
 const releases=useQuery({queryKey:["production-releases",projectId,reviewId],queryFn:()=>request<{id:string;title:string;url:string;kind:string;review_id?:string;created_at:string}[]>(`/production/projects/${projectId}/releases${reviewId?`?review_id=${reviewId}`:''}`),refetchInterval:120000});
 if(releases.error)return <p role="alert">Unable to load shared videos: {releases.error.message}</p>;
 if(!releases.data?.length)return null;
 return <section className="style-panel" data-editor-copy-exclude><h2>Videos from your Editor</h2><p>Shared clips and stitched films. Your original videos remain separate.</p>{releases.data.map(r=><article className="editor-version-card" key={r.id}><strong className="editor-version-badge">FROM YOUR EDITOR · {r.kind==='clip'?'VIDEO CLIP':'STITCHED FILM'}</strong><h3>{r.title}</h3><video src={r.url} controls preload="metadata" style={{width:"100%",maxWidth:720}}/><p>Shared {new Date(r.created_at).toLocaleString()}</p><a href={r.url}>Download {r.kind==='clip'?'video clip':'stitched video'}</a>{r.review_id&&!reviewId&&<p><Link href={`/projects/${projectId}/editor-versions/${r.review_id}`}>View the associated editor version</Link></p>}</article>)}</section>;
}
