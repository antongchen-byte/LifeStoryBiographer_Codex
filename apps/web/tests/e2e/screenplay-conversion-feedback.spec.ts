import {test,expect} from '@playwright/test';
test('conversion explains consent and displays submission failures beside the action',async({page})=>{
 let submitted=0;
 const draft={id:'draft',title:'Fixture',interview_uid:'interview',project_id:'project',session_id:null,source:{},reviewed_markdown:'A reviewed conversation.',materials:[],revision:0,state:'idle',sections:[],progress:0,draft_stale:false,exports:[]};
 await page.route('**/api/auth/session',r=>r.fulfill({json:{user:{email:'fixture@example.com',name:'Fixture'},expires:'2099-01-01T00:00:00Z'}}));
 await page.route('**/api/backend/**',r=>{
  const path=new URL(r.request().url()).pathname;
  if(path.endsWith('/generate')){submitted++;return r.fulfill({status:503,json:{detail:'Generation service unavailable. Please retry.'}});}
  const body=path.endsWith('/production/me')?{production_editor:false}:path.endsWith('/screenplays/draft')?draft:[];
  return r.fulfill({json:body});
 });
 await page.goto('/screenplay-editor?screenplay=draft');
 const panel=page.locator('section').filter({has:page.getByRole('heading',{name:'2. Draft and review the screenplay',exact:true})});
 const button=panel.getByRole('button',{name:'Convert conversation to screenplay draft'});
 await button.click();
 await expect(panel.getByRole('alert')).toContainText('Select ‘Allow Gemini');
 expect(submitted).toBe(0);
 await panel.getByLabel('Allow Gemini to process').check();
 await button.click();
 await expect(panel.getByRole('alert')).toContainText('Generation service unavailable');
 expect(submitted).toBe(1);
 await expect(button).toBeEnabled();
});
