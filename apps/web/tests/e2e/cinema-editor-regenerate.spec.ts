import {test,expect} from '@playwright/test';
test('editor can regenerate an unsatisfactory clip with an edited prompt',async({page})=>{
 let submitted:any=null;
 const clip={id:'old-clip',kind:'clip',state:'ready',previewed:true,approved:false,duration:8,frame_ready:true,preview_url:'https://storage.test/clip.mp4',download_url:'https://storage.test/clip.mp4',request:{prompt:'Original prompt',continuity:'A garden',material_ids:[],material_variants:{}}};
 let production:any={id:'production',screenplay_id:'draft',title:'Editor draft',revision:1,interview_uid:'interview',all_approved:false,materials:[],renders:[],units:[{id:'unit',position:1,section_position:1,seconds:8,prompt:'Original prompt',content:{material_ids:[],elements:[{kind:'scene',text:'EXT. GARDEN - DAY'}]},stale:false,clip}]};
 await page.addInitScript(()=>sessionStorage.setItem('production-project',JSON.stringify({id:'project',actor_id:'editor',title:'Story',owner_name:'Owner'})));
 await page.route('**/api/auth/session',r=>r.fulfill({json:{user:{email:'editor@example.com',name:'Editor'},expires:'2099-01-01T00:00:00Z'}}));
 await page.route('**/api/backend/**',r=>{
  const path=new URL(r.request().url()).pathname;
  if(path.endsWith('/production/me'))return r.fulfill({json:{production_editor:true,actor_id:'editor'}});
  if(path.endsWith('/interviews/screenplays'))return r.fulfill({json:[{id:'draft',title:'Editor draft',revision:1,cinema_ready:true}]});
  if(path.endsWith('/generate')){submitted=r.request().postDataJSON();expect(r.request().headers()['x-production-project']).toBe('project');production={...production,units:[{...production.units[0],clip:{...clip,id:'replacement',state:'pending',request:submitted}}]};}
  return r.fulfill({json:production});
 });
 page.on('dialog',d=>d.accept());
 await page.goto('/cinema-studio?screenplay=draft');
 await page.getByRole('button',{name:'No, revise this clip',exact:true}).click();
 const retry=page.getByRole('button',{name:'Regenerate with edited prompt',exact:true});
 await expect(retry).toBeDisabled();
 await page.getByLabel('Video prompt for subsection 1.1').fill('Revised prompt: show the gardener opening the gate.');
 await page.getByLabel('Allow paid Gemini Omni regeneration for this session').check();
 await expect(retry).toBeEnabled();
 await retry.click();
 await expect(page.getByText('Video job: pending')).toBeVisible();
 expect(submitted.prompt).toBe('Revised prompt: show the gardener opening the gate.');
 expect(submitted.expected_clip_id).toBe('old-clip');
 expect(submitted.consent).toBe(true);
});
