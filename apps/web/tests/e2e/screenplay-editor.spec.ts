import { test, expect } from "@playwright/test";
import { readFile, mkdir } from "node:fs/promises";
const origin = { Origin: "http://localhost:3000" };
const content = (text = "A FAMILY PHOTO fills the screen.") => ({
  elements: [
    { kind: "scene", text: "INT. FAMILY HOME - DAY" },
    { kind: "action", text },
    { kind: "character", text: "NARRATOR (V.O.)" },
    { kind: "parenthetical", text: "(quietly)" },
    { kind: "dialogue", text: "I remember our garden." },
    { kind: "transition", text: "FADE OUT." },
  ],
  notes: "Proposed visual staging.",
  material_ids: [],
});

test("load interview and Markdown, edit screenplay and timed subsections, export and reopen", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/login");
  await page
    .getByRole("button", { name: "Create an account", exact: true })
    .click();
  await page.getByLabel("Your name").fill("Screenplay tester");
  await page
    .getByLabel("Email address")
    .fill(`screenplay-${Date.now()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-screenplay-password");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "My biographies" }),
  ).toBeVisible();
  const project = (
    await (
      await page.request.post("/api/backend/projects", {
        headers: origin,
        data: {
          subject_name: "Screenplay fixture",
          title: "Screenplay fixture",
        },
      })
    ).json()
  ).id;
  const config = (
    await (
      await page.request.post("/api/backend/interviews/configs", {
        headers: origin,
        data: { project_id: project, avatar: "flame", name: "Ember" },
      })
    ).json()
  ).id;
  const session = (
    await (
      await page.request.post("/api/backend/interviews/sessions", {
        headers: origin,
        data: {
          config_id: config,
          title: "Garden story",
          provider_consent: true,
          start_with_greeting: true,
        },
      })
    ).json()
  ).id;
  expect(
    (
      await page.request.post(
        `/api/backend/interviews/sessions/${session}/finish`,
        { headers: origin, data: {} },
      )
    ).ok(),
  ).toBeTruthy();
  await page.goto(`/interview-studio/${session}/review`);
  await page
    .getByRole("button", { name: "Proceed to Screenplay Editor" })
    .click();
  await expect(page.getByLabel("Conversation Markdown")).toHaveValue(
    /Garden story/,
  );
  await expect(page).toHaveURL(/screenplay-editor\?screenplay=/);
  const databaseScreenplay = new URL(page.url()).searchParams.get(
    "screenplay",
  )!;
  expect(
    (
      await page.request.get(
        `/api/backend/interviews/screenplays/${databaseScreenplay}`,
      )
    ).ok(),
  ).toBeTruthy();
  // The separate page also supports database selection and local Markdown imports.
  await page.getByLabel("Database interview").selectOption(session);
  await page.getByText("Import a saved Markdown file", { exact: true }).click();
  await page.getByLabel("Biography workspace").selectOption(project);
  await page.getByLabel("Saved interview Markdown").setInputFiles({
    name: "garden-interview.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      `# Garden interview\n\nInterview UID: ${session}\n\nI remember our garden.`,
    ),
  });
  await page
    .getByRole("button", { name: "Load Markdown", exact: true })
    .click();
  await expect(page.getByLabel("Conversation Markdown")).toHaveValue(
    new RegExp("I remember our garden"),
  );
  const id = new URL(page.url()).searchParams.get("screenplay")!;
  expect(id).not.toBe(databaseScreenplay);
  await page
    .getByLabel("Conversation Markdown")
    .fill(`# Garden\nInterview UID: ${session}\nMy father tended the garden.`);
  await page.getByRole("button", { name: "Save source and edits" }).click();
  await expect(
    page.getByText("Conversation and screenplay edits saved.", { exact: true }),
  ).toBeVisible();
  const real = await page.request.get(
    `/api/backend/interviews/screenplays/${id}`,
  );
  let state = await real.json();
  expect(state.reviewed_markdown).toContain("My father tended");
  // Provider-dependent generation and subsequent preview edits use deterministic fixtures.
  await page.route(
    `**/api/backend/interviews/screenplays/${id}**`,
    async (route) => {
      const req = route.request(),
        path = new URL(req.url()).pathname;
      if (req.method() === "DELETE") return route.continue();
      if (path.endsWith("/generate")) {
        const body = req.postDataJSON();
        expect(body.consent).toBeTruthy();
        if (body.kind === "draft") {
          state.sections = [
            {
              id: "section-1",
              position: 1,
              seconds: 60,
              content: content(),
              subsections: [],
              breakdown_stale: false,
            },
          ];
        } else {
          state.sections[0].subsections = Array.from(
            { length: 60 / body.seconds },
            (_, i) => ({
              id: `sub-${i}`,
              position: i + 1,
              seconds: body.seconds,
              start_seconds: i * body.seconds,
              content: content(`Garden detail ${i + 1}.`),
            }),
          );
        }
        state.state = "idle";
        state.revision++;
      } else if (req.method() === "PUT") {
        const body = req.postDataJSON();
        state = {
          ...state,
          ...body,
          sections: body.sections.map((p: any, i: number) => ({
            ...state.sections[i],
            ...p,
            subsections: p.subsections.map((sub: any, j: number) => ({
              ...state.sections[i].subsections[j],
              ...sub,
            })),
          })),
          revision: state.revision + 1,
        };
      } else if (path.endsWith("/export")) {
        return route.fulfill({
          json: {
            filename: `screenplay-${session}.md`,
            markdown: `# Screenplay\nInterview UID: ${session}\nSection UID: section-1\nSubsection UID: sub-0\n${state.sections[0].subsections[0].content.elements[1].text}`,
          },
        });
      }
      await route.fulfill({ json: state });
    },
  );
  await page.getByLabel("Number of 60-second sections").fill("1");
  await page.getByLabel(/Allow Gemini to process/).check();
  await page
    .getByRole("button", { name: "Convert conversation to screenplay draft" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Section 1 · approximately 60 seconds" }),
  ).toBeVisible();
  await expect(
    page.locator(".screenplay-paper .screenplay-scene").first(),
  ).toHaveCSS("text-transform", "uppercase");
  await expect(
    page.locator(".screenplay-paper .screenplay-character").first(),
  ).toHaveCSS("text-align", "center");
  await expect(
    page.locator(".screenplay-paper .screenplay-transition").first(),
  ).toHaveCSS("text-align", "right");
  await page.getByText("Edit section 1", { exact: true }).click();
  await page
    .getByLabel("Section 1 element 2 text", { exact: true })
    .fill("A SUNLIT PHOTO fills the screen.");
  await page
    .getByRole("button", { name: "Save section 1", exact: true })
    .click();
  await expect(
    page.getByText("Section 1 saved.", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Subsection duration").selectOption("15");
  await page
    .getByRole("button", { name: "Break into video subsections" })
    .click();
  await expect(
    page.getByText("Subsection 1.4 · 45–60s", { exact: true }),
  ).toBeVisible();
  await page.getByText("Subsection 1.1 · 0–15s", { exact: true }).click();
  await page
    .getByLabel("Subsection 1.1 element 2 text", { exact: true })
    .fill("A HAND holds the family photograph.");
  await page
    .getByRole("button", { name: "Save subsection 1.1", exact: true })
    .click();
  await expect(
    page.getByText("Subsection 1.1 saved.", { exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page
    .getByRole("button", {
      name: "Save final screenplay and download Markdown",
    })
    .click();
  const result = await download;
  const text = await readFile((await result.path())!, "utf8");
  expect(text).toContain(session);
  expect(text).toContain("A HAND holds");
  await page.reload();
  await page.getByText("Subsection 1.1 · 0–15s", { exact: true }).click();
  await expect(
    page.getByLabel("Subsection 1.1 element 2 text", { exact: true }),
  ).toHaveValue("A HAND holds the family photograph.");
  await mkdir("/private/tmp/lifestory-previews", { recursive: true });
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/screenplay-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/screenplay-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
  await page.unrouteAll({ behavior: "wait" });
  for (const sid of [databaseScreenplay, id])
    expect(
      (
        await page.request.delete(
          `/api/backend/interviews/screenplays/${sid}`,
          { headers: origin },
        )
      ).ok(),
    ).toBeTruthy();
  await page.request.delete(`/api/backend/interviews/sessions/${session}`, {
    headers: origin,
  });
  await page.request.delete(`/api/backend/interviews/configs/${config}`, {
    headers: origin,
  });
  await page.request.delete(`/api/backend/projects/${project}`, {
    headers: origin,
  });
});
