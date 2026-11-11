import {test,expect} from '@playwright/test';
test('owner can preview and download editor clips and stitched films',async({page})=>{
 await page.route('**/api/auth/session',r=>r.fulfill({json:{user:{email:'owner@example.com',name:'Owner'},expires:'2099-01-01T00:00:00Z'}}));
 await page.route('**/api/backend/**',r=>{
  const path=new URL(r.request().url()).pathname;
  let body:any=[];
  if(path.endsWith('/production/me'))body={production_editor:false,actor_id:'owner'};
  if(path.endsWith('/projects/project'))body={id:'project',title:'Biography',subject_name:'Owner',description:'Original',role:'OWNER',status:'intake',media_count:0};
  if(path.endsWith('/releases'))body=[{id:'clip',title:'Clip 1.1',kind:'clip',review_id:'review',url:'https://storage.test/shared-clip.mp4',created_at:'2026-11-09T12:00:00Z'},{id:'film',title:'Finished film',kind:'stitch',review_id:'review',url:'https://storage.test/shared-film.mp4',created_at:'2026-11-09T12:00:00Z'}];
  if(path.endsWith('/reviews/review'))body={id:'review',title:'Editor version',content:'Saved page',created_at:'2026-11-09T12:00:00Z',editor_name:'Editor',version_number:1,module:'cinema',can_create_project:true};
  return r.fulfill({json:body});
 });
 for(const url of ['/projects/project','/projects/project/editor-versions/review']){
  await page.goto(url);
  await expect(page.getByRole('heading',{name:'Videos from your Editor'})).toBeVisible();
  await expect(page.locator('video')).toHaveCount(2);
  await expect(page.getByRole('link',{name:'Download video clip',exact:true})).toHaveAttribute('href','https://storage.test/shared-clip.mp4');
  await expect(page.getByRole('link',{name:'Download stitched video',exact:true})).toHaveAttribute('href','https://storage.test/shared-film.mp4');
 }
});
