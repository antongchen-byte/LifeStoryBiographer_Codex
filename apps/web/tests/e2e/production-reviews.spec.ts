import {test,expect} from '@playwright/test';
test('editor shares unsaved field values without overwriting owner content',async({page})=>{
 let editor=true, writes=0;
 let shared:any=null;
 await page.addInitScript(()=>sessionStorage.setItem('production-project',JSON.stringify({id:'project',title:'Original title',actor_id:'actor',owner_name:'Owner'})));
 await page.route('**/api/auth/session',r=>r.fulfill({json:{user:{email:'actor@example.com',name:'Actor'},expires:'2099-01-01T00:00:00Z'}}));
 await page.route('**/api/backend/**',async r=>{
  const path=new URL(r.request().url()).pathname.replace('/api/backend','');
  if(r.request().method()==='PATCH'||r.request().method()==='PUT')writes++;
  const project={id:'project',title:'Original title',subject_name:'Owner',description:'Original description',role:editor?'PRODUCTION_EDITOR':'OWNER',status:'intake',media_count:0};
  let body:any=[];
  if(path==='/production/me')body={production_editor:editor,actor_id:'actor'};
  if(path==='/interviews/options')body={avatars:{flame:'Ember'},genres:{life_story:'Life story'},personalities:{},provider_ready:false,voice_ready:false};
  if(path==='/projects')body=[project];
  if(path==='/projects/project')body=project;
  if(path==='/production/projects/project/reviews'){
   if(r.request().method()==='POST'){shared={...r.request().postDataJSON(),id:'version',editor_name:'Assigned Editor',version_number:1,created_at:'2026-11-08T12:00:00Z'};body=shared;}else body=shared?[shared]:[];
  }
  if(path==='/production/projects/project/reviews/version')body=shared;
  return r.fulfill({json:body});
 });
 await page.goto('/projects/project');
 await page.getByLabel('Description',{exact:true}).fill('A new description in the editor copy.');
 await page.getByRole('button',{name:'Save editor version for owner',exact:true}).click();
 const preview=page.getByRole('region',{name:'Preview editor version'});
 await expect(preview).toContainText('A new description in the editor copy.');
 await page.getByRole('button',{name:'Confirm and share version'}).click();
 await expect(page.getByText('Saved as a separate owner-visible version.',{exact:false})).toBeVisible();
 expect(shared.content).toContain('A new description in the editor copy.');
 expect(writes).toBe(0);
 for(const path of ['/','/style-lab','/interview-studio','/screenplay-editor','/cinema-studio']){
  await page.goto(path);
  await expect(page.getByRole('button',{name:'Save editor version for owner',exact:true})).toBeVisible();
 }
 editor=false;
 await page.goto('/projects/project');
 await expect(page.getByLabel('Description',{exact:true})).toHaveValue('Original description');
 await expect(page.getByRole('button',{name:'Save editor version for owner',exact:true})).toHaveCount(0);
 await expect(page.getByText('Your working biography',{exact:true})).toBeVisible();
 await expect(page.getByRole('link',{name:'Editor-1 — My Biographies',exact:true})).toHaveCount(0);
 await page.getByRole('link',{name:'Review editor versions →',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Versions from your Editor'})).toBeVisible();
 await expect(page.getByLabel('Description',{exact:true})).toHaveCount(0);
 await expect(page.getByText('Assigned Editor',{exact:true})).toBeVisible();
 await page.getByRole('link',{name:'Editor-1 — My Biographies',exact:true}).click();
 await expect(page.getByText('EDITOR COPY · READ ONLY',{exact:true})).toBeVisible();
 await expect(page.getByText('A new description in the editor copy.',{exact:false})).toBeVisible();
 await expect(page.locator('textarea,input')).toHaveCount(0);
});
