"use client";
import {useFilmAccess} from "../lib/film-access";
import Link from 'next/link';
import {useEffect,useState} from 'react';
import {Button} from './ui/button';
export default function WorkingContext(){
 const filmAllowed=useFilmAccess();
 const [context,setContext]=useState<{id:string;title:string;config_id?:string;screenplay_id?:string}|null>(null);
 useEffect(()=>{const refresh=()=>{const raw=sessionStorage.getItem('working-project');setContext(raw?JSON.parse(raw):null);};refresh();window.addEventListener('working-context-updated',refresh);return()=>window.removeEventListener('working-context-updated',refresh);},[]);
 if(!context)return null;
 return <aside className="editor-versions-entry"><strong>Isolated editable project: {context.title}</strong><p>All modules are scoped to this project. The original biography and shared editor version remain separate.</p><nav className="interview-toolbar"><Link href={`/projects/${context.id}`}>My Biographies</Link><Link href={context.config_id?`/style-lab?config=${context.config_id}`:'/style-lab'}>Style Lab</Link><Link href={context.config_id?`/interview-studio?config=${context.config_id}`:'/interview-studio'}>Interview Studio</Link>{filmAllowed && <><Link href={context.screenplay_id?`/screenplay-editor?screenplay=${context.screenplay_id}`:'/screenplay-editor'}>Screenplay Editor</Link><Link href={context.screenplay_id?`/cinema-studio?screenplay=${context.screenplay_id}`:'/cinema-studio'}>Cinema Studio</Link></>}</nav><Button variant="outline" onClick={()=>{sessionStorage.removeItem('working-project');window.location.assign('/');}}>Exit isolated project</Button></aside>;
}
