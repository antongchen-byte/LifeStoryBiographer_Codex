"use client";
import {useEffect,useState} from "react";
import {usePathname} from "next/navigation";
import Link from "next/link";
import {request} from "../lib/api";
import {editorPageCopy} from "../lib/editor-page-copy";
import {Button} from "./ui/button";
export default function ProductionShare(){
 const path=usePathname();
 const [context,setContext]=useState<{id:string;title:string}|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(""),[saved,setSaved]=useState("");
 const [preview,setPreview]=useState<{content:string;request_id:string;projectId:string;module:string;screenplay_id?:string;screenplay_revision?:number;session_id?:string}|null>(null);
 useEffect(()=>{const refresh=()=>{const raw=sessionStorage.getItem("production-project");setContext(raw?JSON.parse(raw):null);};refresh();setPreview(null);setError("");setSaved("");window.addEventListener("production-context-updated",refresh);return()=>window.removeEventListener("production-context-updated",refresh);},[path]);
 const module=path.startsWith('/style-lab')?'style':path.startsWith('/interview-studio')?'interview':path.startsWith('/screenplay-editor')?'screenplay':path.startsWith('/cinema-studio')?'cinema':(path==='/' || (path.startsWith('/projects/')&&!path.includes('/editor-versions')))?'biography':null;
 if(!context || !module)return null;
 const names:Record<string,string>={biography:'My Biographies',style:'Style Lab',interview:'Interview Studio',screenplay:'Screenplay Editor',cinema:'Cinema Studio'};
 return <section className="style-panel" aria-label="Share editor version" data-editor-copy-exclude>
 <h2>Save a version for the owner</h2><p>Save this page’s text and current field values as a separate, read-only review copy. The owner’s working version stays unchanged. The editable project copy uses saved module records. Save module edits, finish uploads and generation, then share; unsaved fields appear only in the read-only page copy.</p>
 <Button disabled={busy} onClick={async()=>{setBusy(true);setError('');setSaved('');try{
 const root=document.getElementById('module-page-content');if(!root)throw Error('Wait for the page to load.');
 const content=editorPageCopy(root);if(!content)throw Error('Wait for the page content to load before saving.');
 const current=JSON.parse(sessionStorage.getItem('production-project')||'{}');
 const screenplayId=['screenplay','cinema'].includes(module)?new URLSearchParams(window.location.search).get('screenplay'):current.screenplay_id;
 if(['screenplay','cinema'].includes(module)&&!screenplayId)throw Error('Load the screenplay you want to share first.');
 const screenplay=screenplayId?await request<{id:string;revision:number;project_id:string}>(`/interviews/screenplays/${screenplayId}`):null;
 if(screenplay&&screenplay.project_id!==context.id)throw Error('The displayed screenplay belongs to another project.');
 const sessionId=module==='interview'?path.match(/^\/interview-studio\/([^/]+)/)?.[1]:undefined;
 setPreview({content,request_id:crypto.randomUUID(),projectId:context.id,module,screenplay_id:screenplay?.id,screenplay_revision:screenplay?.revision,session_id:sessionId});
 }catch(e){setError(e instanceof Error?e.message:'Unable to prepare the version');}finally{setBusy(false);}}}>Save editor version for owner</Button>
 {preview && <div role="region" aria-label="Preview editor version"><h3>Review the copy to share</h3>{preview.screenplay_id&&<p>Screenplay UID: {preview.screenplay_id} · Saved revision: {preview.screenplay_revision}</p>}<p>Unrelated active interviews are excluded. Save any unsaved module edits before preparing this preview.</p><pre style={{whiteSpace:'pre-wrap',maxHeight:360,overflow:'auto'}}>{preview.content}</pre><Button disabled={busy} onClick={async()=>{setBusy(true);setError('');try{const current=JSON.parse(sessionStorage.getItem('production-project')||'null');if(current?.id!==preview.projectId)throw Error('The selected project changed. Reopen the preview.');if(['screenplay','cinema'].includes(preview.module)&&new URLSearchParams(window.location.search).get('screenplay')!==preview.screenplay_id)throw Error('The selected screenplay changed. Reopen the preview.');const result=await request<{id:string}>(`/production/projects/${preview.projectId}/reviews`,{method:'POST',body:JSON.stringify({module:preview.module,screenplay_id:preview.screenplay_id,screenplay_revision:preview.screenplay_revision,session_id:preview.session_id,title:`Editor-${names[preview.module]} — ${context.title}`.slice(0,200),content:preview.content,request_id:preview.request_id})});setSaved(`/projects/${preview.projectId}/editor-versions/${result.id}`);setPreview(null);window.dispatchEvent(new Event('production-review-shared'));}catch(e){setError(e instanceof Error?e.message:'Unable to save the editor version.');}finally{setBusy(false);}}}>{busy?'Saving…':'Confirm and share version'}</Button><Button variant="outline" disabled={busy} onClick={()=>setPreview(null)}>Cancel</Button></div>}
 {error&&<p role="alert">{error}</p>}{saved&&<p role="status">Saved as a separate owner-visible version. <Link href={saved}>View shared version</Link></p>}
 </section>;
}
