import {test,expect} from '@playwright/test';
test('Cinema sharing pins the displayed screenplay instead of stale editor context',async({page})=>{
 let submitted:any;
 await page.addInitScript(()=>sessionStorage.setItem('production-project',JSON.stringify({id:'project',title:'Story',actor_id:'editor',owner_name:'Owner',screenplay_id:'old-screenplay'})));
 await page.route('**/api/auth/session',r=>r.fulfill({json:{user:{email:'editor@example.com',name:'Editor'},expires:'2099-01-01T00:00:00Z'}}));
 await page.route('**/api/backend/**',r=>{
  const path=new URL(r.request().url()).pathname.replace('/api/backend','');
  let body:any=[];
  if(path==='/production/me')body={production_editor:true,actor_id:'editor'};
  if(path==='/interviews/screenplays')body=[{id:'displayed-screenplay',title:'Current film',revision:7,cinema_ready:true}];
  if(path==='/interviews/screenplays/displayed-screenplay')body={id:'displayed-screenplay',project_id:'project',revision:7};
  if(path.startsWith('/cinema/'))body={id:'production',screenplay_id:'displayed-screenplay',title:'Current film',revision:7,interview_uid:'interview',all_approved:false,materials:[],units:[],renders:[]};
  if(path==='/production/projects/project/reviews'&&r.request().method()==='POST'){submitted=r.request().postDataJSON();body={id:'shared'};}
  return r.fulfill({json:body});
 });
 await page.goto('/cinema-studio?screenplay=displayed-screenplay');
 await expect(page.getByRole('heading',{name:'Current film',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Save editor version for owner',exact:true}).click();
 await expect(page.getByRole('region',{name:'Preview editor version'})).toContainText('Screenplay UID: displayed-screenplay · Saved revision: 7');
 await page.getByRole('button',{name:'Confirm and share version',exact:true}).click();
 await expect(page.getByRole('link',{name:'View shared version',exact:true})).toBeVisible();
 expect(submitted.screenplay_id).toBe('displayed-screenplay');
 expect(submitted.screenplay_revision).toBe(7);
 expect(submitted.title).toMatch(/^Editor-/);
});
