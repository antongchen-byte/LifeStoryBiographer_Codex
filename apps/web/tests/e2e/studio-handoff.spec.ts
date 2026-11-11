import { test, expect } from "@playwright/test";

test("Style Lab configuration hands off to a focused Interview Studio", async ({ page }) => {
  const config = {id:"configured",name:"Maya",avatar:"female",genre:"life_story",project_id:"biography",created_at:"2026-11-02T12:00:00Z"};
  await page.route("**/api/auth/session", r=>r.fulfill({json:{user:{id:"user",email:"fixture@example.com"},expires:"2099-01-01T00:00:00Z"}}));
  await page.route("**/api/backend/**", r=> {
    const path=new URL(r.request().url()).pathname.replace("/api/backend", "");
    let body: unknown=[];
    if(path === "/interviews/sessions" && r.request().method() === "POST" || path === "/interviews/sessions/inline-session") body={id:"inline-session",project_id:"biography",config_id:"configured",name:"Maya",avatar:"female",avatar_id:"avatar",title:"My life story",status:"active",revision:1,model:"fixture",busy:false,turns:[],approvals:[]};
    if(path==="/projects") body=[{id:"biography",title:"My story",role:"OWNER"}];
    if(path==="/interviews/options") body={avatars:{flame:"Ember",female:"Maya",male:"Eli"},genres:{life_story:"Life story"},personalities:{},provider_ready:true};
    if(path==="/interviews/configs") body=[config];
    if(path==="/interviews/configs/configured/markdown") body={filename:"maya.md",markdown:"# Maya\nA thoughtful interviewer."};
    return r.fulfill({json:body});
  });
  await page.goto("/style-lab");
  await expect(page.getByRole("heading",{name:"Configure your interviewer",exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"Create transcript",exact:true})).toHaveCount(0);
  await page.getByRole("combobox",{name:"Configured interviewer",exact:true}).selectOption("configured");
  await page.getByText("Preview saved interviewer Markdown",{exact:true}).click();
  await expect(page.getByText("# Maya",{exact:false})).toBeVisible();
  await page.getByRole("button",{name:"Proceed to Interview Studio"}).click();
  await expect(page).toHaveURL(/interview-studio\?config=configured/);
  await expect(page.getByText("Maya",{exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"Upload reference templates",exact:true})).toHaveCount(0);
  await expect(page.getByRole("combobox",{name:"Configured interviewer",exact:true})).toHaveCount(0);
  await page.getByRole("checkbox",{name:/I authorize sending selected references/}).check();
  await expect(page.getByRole("button",{name:"Start interview",exact:true})).toBeEnabled();
  await expect(page.getByRole("combobox",{name:"Saved interviews",exact:true})).toBeVisible();
  const url = page.url();
  await page.getByRole("button",{name:"Start interview",exact:true}).click();
  await expect(page.locator("#active-interview")).toBeVisible();
  await expect(page.getByRole("complementary",{name:"Interviewer avatar and playback"})).toBeVisible();
  await expect(page.getByRole("heading",{name:"Your turn",exact:true})).toBeVisible();
  await expect(page).toHaveURL(url);
  await page.getByRole("button",{name:"Back to Interview Studio",exact:true}).click();
  await expect(page.getByRole("button",{name:"Start interview",exact:true})).toBeVisible();
});
