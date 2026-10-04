import { test, expect } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";

test.use({
  launchOptions: {
    args: [
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
    ],
  },
  permissions: ["microphone"],
});

test("configure a real interviewer, then exercise voice, chat and approval UI with deterministic provider fixtures", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/login");
  await page
    .getByRole("button", { name: "Create an account", exact: true })
    .click();
  await page.getByLabel("Your name").fill("Interview Studio Tester");
  await page
    .getByLabel("Email address")
    .fill(`interview-${Date.now()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-interview-password");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "My biographies" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "New biography" }).click();
  await page.getByLabel("Subject’s name").fill("Interview fixture");
  await page.getByLabel("Biography title").fill("Interview fixture biography");
  await page
    .getByRole("button", { name: "Create biography", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Interview fixture biography" }),
  ).toBeVisible();
  await page.goto("/interview-studio");
  await expect(
    page.getByRole("heading", { name: "A conversation worth keeping" }),
  ).toBeVisible();
  await expect(page.getByLabel("Biography workspace")).not.toHaveValue("");
  const project = await page.getByLabel("Biography workspace").inputValue();
  await expect(page.getByText("Calm and reflective", { exact: true })).toBeVisible();
  await expect(page.getByText("Warm and curious", { exact: true })).toBeVisible();
  await expect(page.getByText("Thoughtful and focused", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Female face/ }).click();
  await expect(page.getByLabel("Interviewer name")).toHaveValue("Maya");
  await page.getByRole("button", { name: /Male face/ }).click();
  await expect(page.getByLabel("Interviewer name")).toHaveValue("Eli");
  await page.getByRole("button", { name: /Candle flame/ }).click();
  await page.getByLabel("Interviewer name").fill("Memory Keeper");
  await page.getByLabel("Interview genre").selectOption("oral_history");
  const downloaded = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Save interviewer & generate Markdown" })
    .click();
  const file = await downloaded;
  const content = await readFile((await file.path())!, "utf8");
  expect(content).toContain("Memory Keeper");
  expect(content).toContain("Avatar ID:");
  expect(content).toContain("oral_history");
  expect(content).toContain("Calm and reflective");
  await expect(page.getByLabel("Configured interviewer")).not.toHaveValue("");
  const config = await page.getByLabel("Configured interviewer").inputValue();
  expect(content).toContain(config);
  await mkdir("/private/tmp/lifestory-previews", { recursive: true });
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/interview-setup-desktop.png",
    fullPage: true,
  });
  await page.getByLabel(/I authorize sending/).check();
  await page
    .getByRole("button", { name: "Start interview", exact: true })
    .click();
  await expect(
    page.getByText("Ready to listen", { exact: true }),
  ).toBeVisible();
  const sid = await page.getByLabel("Saved interviews").inputValue();
  const stateResponse = await page.request.get(
    `/api/backend/interviews/sessions/${sid}`,
  );
  expect(stateResponse.ok()).toBeTruthy();
  const state = await stateResponse.json();
  let audioReceived = false;
  // Only provider-dependent conversation endpoints use fixtures. Configuration,
  // authentication, session creation and cleanup above/below use the real stack.
  await page.route(
    `**/api/backend/interviews/sessions/${sid}**`,
    async (route) => {
      const req = route.request();
      const pathname = new URL(req.url()).pathname;
      const body = req.method() === "GET" ? {} : req.postDataJSON();
      if (pathname.endsWith("/turns") && req.method() === "POST") {
        audioReceived ||= !!body.audio;
        const seq = state.turns.length + 1;
        state.turns.push({
          id: `turn-${seq}`,
          request_id: body.request_id,
          sequence: seq,
          role: "user",
          text: body.text || "A recorded garden memory.",
          original_text: body.text || "A recorded garden memory.",
          state: "complete",
          has_audio: !!body.audio,
          citations: [],
          error: null,
          created_at: new Date().toISOString(),
        });
        state.turns.push({
          id: `turn-${seq + 1}`,
          request_id: body.request_id,
          sequence: seq + 1,
          role: "assistant",
          text: "Who was with you in the garden?",
          original_text: "Who was with you in the garden?",
          state: "complete",
          has_audio: false,
          citations: [],
          error: null,
          created_at: new Date().toISOString(),
        });
        state.revision++;
      } else if (pathname.endsWith("/finish")) {
        state.status = "review";
        state.revision++;
      } else if (req.method() === "PATCH") {
        state.turns.find((t: any) => pathname.endsWith(t.id)).text = body.text;
        state.revision++;
      } else if (pathname.endsWith("/approve")) {
        state.status = "approved";
        state.approvals = [
          { id: "approved-fixture", revision: state.revision },
        ];
      } else if (pathname.endsWith("/export")) {
        return route.fulfill({
          json: {
            filename: `interview-${sid}`,
            markdown: "# Approved fixture",
            snapshot: state,
          },
        });
      }
      await route.fulfill({ json: state });
    },
  );
  await page.getByLabel(/Speak replies and retain/).uncheck();
  await page.getByLabel("Your message").fill("I remember our garden.");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByText("Who was with you in the garden?", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Record voice turn", exact: true })
    .click();
  await expect(
    page.getByText("Listening and recording…", { exact: true }),
  ).toBeVisible({ timeout: 15000 });
  await page.waitForTimeout(1200);
  await page
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Send recorded voice turn" }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Send recorded voice turn" }).click();
  await expect(
    page.getByText("A recorded garden memory.", { exact: true }),
  ).toBeVisible();
  expect(audioReceived).toBeTruthy();
  await page
    .getByRole("button", { name: "Finish & review conversation" })
    .click();
  await expect(
    page.getByText("Review the conversation", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Edit transcript turn" })
    .first()
    .click();
  await page
    .getByLabel("Corrected text for turn 1")
    .fill("I remember our railway garden.");
  await page.getByRole("button", { name: "Save correction" }).click();
  await expect(
    page.getByText("I remember our railway garden.", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/interview-review-desktop.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Approve conversation script" })
    .click();
  await expect(
    page.getByText("Approved interview", { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/interview-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
  expect(errors).toEqual([]);
  await page.unrouteAll();
  expect(
    (
      await page.request.delete(`/api/backend/interviews/sessions/${sid}`, {
        headers: { Origin: "http://localhost:3000" },
      })
    ).status(),
  ).toBe(204);
  expect(
    (
      await page.request.delete(`/api/backend/interviews/configs/${config}`, {
        headers: { Origin: "http://localhost:3000" },
      })
    ).status(),
  ).toBe(204);
  expect(
    (
      await page.request.delete(`/api/backend/projects/${project}`, {
        headers: { Origin: "http://localhost:3000" },
      })
    ).status(),
  ).toBe(204);
});
