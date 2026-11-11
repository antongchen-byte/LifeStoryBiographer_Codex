"use client";
import {useQuery} from '@tanstack/react-query';
import {request} from './api';
export function useFilmAccess(){
 const restricted=process.env.NEXT_PUBLIC_FILM_STUDIOS_EDITOR_ONLY==='true';
 const capability=useQuery({queryKey:['production-me'],queryFn:()=>request<{production_editor:boolean}>('/production/me'),enabled:restricted});
 return process.env.NEXT_PUBLIC_ENABLE_FILM_STUDIOS!=='false' && (!restricted || capability.data?.production_editor===true);
}
