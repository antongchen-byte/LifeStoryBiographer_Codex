import {test,expect} from '@playwright/test';

for(const editor of [false,true])test(`${editor?'Editor':'Regular account'} sees only authorized production UI`,async({page})=>{
 let sawContext=false;
 await page.addInitScript(()=>{if(!sessionStorage.getItem('production-project'))sessionStorage.setItem('production-project',JSON.stringify({id:'old',actor_id:'previous-editor'}));});
 await page.route('**/api/auth/session',r=>r.fulfill({json:{user:{id:'actor',email:'actor@example.com',name:'Actor'},expires:'2099-01-01T00:00:00Z'}}));
 await page.route('**/api/backend/**',r=>{
  const path=new URL(r.request().url()).pathname.replace('/api/backend','');
  const project={id:'jane-project',title:'Jane’s story',subject_name:'Jane',role:'PRODUCTION_EDITOR',description:'A life story',status:'intake',media_count:0};
  const selected={...project,owner_name:'Jane',owner_email:'jane@example.com',actor_id:'actor',screenplay_id:'draft'};
  let body:unknown=[];
  if(path==='/production/me')body={production_editor:editor,actor_id:'actor'};
  if(path==='/production/projects')body=[{...selected,readiness:'Screenplay available'}];
  if(path==='/production/projects/jane-project/open'){sawContext=r.request().headers()['x-production-project']==='jane-project';body=selected;}
  if(path==='/projects/jane-project')body=project;
  if(path==='/projects')body=editor?[project]:[];
  return r.fulfill({json:body});
 });
 await page.goto('/');
 const menu=page.getByRole('navigation',{name:'Main navigation'});
 await expect(menu.getByRole('link',{name:'My biographies',exact:true})).toBeVisible();
 await expect(menu.getByRole('link',{name:/Style Lab/})).toBeVisible();
 await expect(menu.getByRole('link',{name:/Interview Studio/})).toBeVisible();
 await expect(menu.getByRole('link',{name:/Screenplay Editor/})).toBeVisible();
 await expect(menu.getByRole('link',{name:/Cinema Studio/})).toBeVisible();
 if(!editor){
  await expect(menu.getByRole('link',{name:'Production projects'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Start a Biography',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>sessionStorage.getItem('production-project'))).toBeNull();
  await page.goto('/production-projects');
  await expect(page.getByText('Production Editor access is required.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Open project'})).toHaveCount(0);
 }else{
  await menu.getByRole('link',{name:'Production projects'}).click();
  await page.getByRole('button',{name:'Open project'}).click();
  await expect(page).toHaveURL(/projects\/jane-project$/);
  expect(sawContext).toBe(true);
  await expect(page.getByRole('region',{name:'Production workspace'})).toContainText('Jane');
  await expect(page.getByRole('link',{name:'Open screenplay',exact:true})).toHaveAttribute('href','/screenplay-editor?screenplay=draft');
  await expect(page.getByRole('button',{name:'Exit production workspace'})).toBeVisible();
 }
});
