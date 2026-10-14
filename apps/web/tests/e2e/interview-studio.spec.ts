import { test, expect } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";

function openingAudio() {
  const wav = Buffer.alloc(44 + 8000);
  wav.write("RIFF");
  wav.writeUInt32LE(wav.length - 8, 4);
  wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(8000, 24);
  wav.writeUInt32LE(16000, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write("data", 36);
  wav.writeUInt32LE(8000, 40);
  return "data:audio/wav;base64," + wav.toString("base64");
}

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
  await expect(
    page.getByText("Calm and reflective", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Warm and curious", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Thoughtful and focused", { exact: true }),
  ).toBeVisible();
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
  await page.route(
    "**/api/backend/interviews/sessions/*/turns/*/speech",
    (route) =>
      route.fulfill({
        json: { url: openingAudio() },
      }),
  );
  await page.getByLabel(/I authorize sending/).check();
  await page
    .getByRole("button", { name: "Start interview", exact: true })
    .click();
  await expect(
    page.getByText("Listening and recording…", { exact: true }),
  ).toBeVisible({ timeout: 15000 });
  await expect(
    page.getByRole("heading", { name: "Your turn", exact: true }),
  ).toBeInViewport();
  await page
    .getByRole("button", { name: "Pause voice conversation", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Discard unsent recording" }),
  ).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Discard unsent recording" }).click();
  await expect(page.getByLabel("Your message")).toBeEnabled();
  await expect(
    page.getByText(/Hello, I.m Memory Keeper, your AI interviewer/),
  ).toBeVisible();
  await expect(page.locator("#active-interview .avatar-flame")).toHaveCSS(
    "animation-name",
    "interview-flicker",
  );
  await expect(page).toHaveURL(/\/interview-studio\/[^/?]+\?begin=1$/);
  const sid = new URL(page.url()).pathname.split("/").at(-1)!;
  await expect(page.getByLabel("Configured interviewer")).toHaveCount(0);
  await expect(
    page.getByRole("complementary", {
      name: "Interviewer avatar and playback",
    }),
  ).toBeInViewport();
  const stateResponse = await page.request.get(
    `/api/backend/interviews/sessions/${sid}`,
  );
  expect(stateResponse.ok()).toBeTruthy();
  const state = await stateResponse.json();
  let audioReceived = false;
  let attached: any[] = [];
  // Only provider-dependent conversation endpoints use fixtures. Configuration,
  // authentication, session creation and cleanup above/below use the real stack.
  await page.route(
    `**/api/backend/interviews/sessions/${sid}**`,
    async (route) => {
      const req = route.request();
      const pathname = new URL(req.url()).pathname;
      const body = req.method() === "GET" ? {} : req.postDataJSON();
      if (pathname.endsWith("/materials")) {
        if (req.method() === "POST") {
          expect(body.asset_ids).toEqual(["asset-fixture"]);
          attached = [
            {
              id: "material-fixture",
              asset_id: "asset-fixture",
              filename: "family-article.txt",
              url: "data:text/plain,Family",
              sha256: "fixture",
              request_id: body.request_id,
              analysis_state: "ready",
              analysis: {
                summary: "This article describes a family garden.",
                question: "Is that accurate, and how would you describe it?",
              },
              confirmation: {},
            },
          ];
          return route.fulfill({ json: state });
        }
        return route.fulfill({ json: attached });
      }
      if (pathname.endsWith("/materials/discuss")) {
        if (!attached[0].discussion_turn_id) {
          const id = "material-discussion";
          state.turns.push({
            id,
            request_id: id,
            sequence: state.turns.length + 1,
            role: "assistant",
            text: "This article describes a family garden. Is that accurate, and how would you describe it?",
            original_text:
              "This article describes a family garden. Is that accurate, and how would you describe it?",
            state: "complete",
            has_audio: false,
            citations: [],
            created_at: new Date().toISOString(),
          });
          attached[0].discussion_turn_id = id;
        }
        return route.fulfill({ json: state });
      }
      if (pathname.endsWith("/bundle"))
        return route.fulfill({ status: 404, json: { detail: "No archive" } });
      if (pathname.endsWith("/decline")) {
        state.upload_requests[0].status = "declined";
        return route.fulfill({ json: state });
      }
      if (pathname.endsWith("/speech")) {
        const wav = Buffer.alloc(44 + 16000);
        wav.write("RIFF");
        wav.writeUInt32LE(wav.length - 8, 4);
        wav.write("WAVEfmt ", 8);
        wav.writeUInt32LE(16, 16);
        wav.writeUInt16LE(1, 20);
        wav.writeUInt16LE(1, 22);
        wav.writeUInt32LE(8000, 24);
        wav.writeUInt32LE(16000, 28);
        wav.writeUInt16LE(2, 32);
        wav.writeUInt16LE(16, 34);
        wav.write("data", 36);
        wav.writeUInt32LE(16000, 40);
        return route.fulfill({
          json: { url: "data:audio/wav;base64," + wav.toString("base64") },
        });
      }
      if (pathname.endsWith("/turns") && req.method() === "POST") {
        audioReceived ||= !!body.audio;
        if (body.text === "I would like to upload a picture.") {
          state.upload_requests = [
            {
              id: "offer-fixture",
              turn_id: "turn-fixture",
              kind: "image",
              status: "pending",
            },
          ];
        }
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
  await page
    .getByLabel("Your message")
    .fill("I would like to upload a picture.");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("button", { name: "No thanks, continue interview" })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  expect(state.upload_requests[0].status).toBe("declined");
  await page.route(
    `**/api/backend/projects/${state.project_id}/media`,
    (route) =>
      route.fulfill({
        json: [
          {
            id: "asset-fixture",
            original_filename: "family-article.txt",
            status: "ready",
            mime_type: "text/plain",
            size_bytes: 6,
          },
        ],
      }),
  );
  await page.getByRole("button", { name: "Add interview materials" }).click();
  await page
    .getByRole("checkbox", { name: "family-article.txt", exact: true })
    .check();
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/interview-materials-dialog.png",
  });
  await page
    .getByRole("button", { name: "Attach selected materials and continue" })
    .click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByText("Supporting materials (1)", { exact: true }).click();
  await expect(
    page.getByRole("link", { name: "family-article.txt" }),
  ).toBeVisible();

  await expect(
    page
      .getByRole("log")
      .getByText(
        "This article describes a family garden. Is that accurate, and how would you describe it?",
        { exact: true },
      ),
  ).toBeVisible();
  expect(attached[0].discussion_turn_id).toBe("material-discussion");
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/interview-material-confirmation.png",
  });
  await page.getByLabel("Your message").fill("I remember our garden.");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(
    page.getByText("Who was with you in the garden?", { exact: true }).last(),
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
  const beforeVoice = state.turns.length;
  await page.evaluate(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      const ctx = new AudioContext();
      await ctx.resume();
      const oscillator = ctx.createOscillator(),
        gain = ctx.createGain();
      const destination = ctx.createMediaStreamDestination();
      oscillator.connect(gain);
      gain.connect(destination);
      gain.gain.setValueAtTime(0.15, ctx.currentTime);
      gain.gain.setValueAtTime(0, ctx.currentTime + 1.8);
      oscillator.start();
      setTimeout(() => {
        oscillator.stop();
        void ctx.close();
      }, 10000);
      return destination.stream;
    };
  });
  await page
    .getByRole("button", { name: "Resume voice conversation", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Send voice answer now" }),
  ).toBeVisible();

  await expect
    .poll(() => state.turns.length, { timeout: 12000 })
    .toBe(beforeVoice + 2);
  await expect(
    page.getByRole("button", { name: "Send voice answer now" }),
  ).toBeVisible({ timeout: 15000 });
  await page.getByRole("button", { name: "Pause voice conversation" }).click();
  await expect(
    page.getByRole("button", {
      name: "Resume voice conversation",
      exact: true,
    }),
  ).toBeVisible();
  const discard = page.getByRole("button", {
    name: "Discard unsent recording",
  });
  await expect(discard).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await discard.click();
  await page
    .getByRole("button", { name: "Resume voice conversation", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Send voice answer now" }),
  ).toBeVisible();
  expect(new URL(page.url()).pathname).toBe(`/interview-studio/${sid}`);
  await page.getByRole("button", { name: "Pause voice conversation" }).click();
  await expect(discard).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await discard.click();
  await expect
    .poll(() =>
      page
        .getByRole("log", { name: "Interview conversation" })
        .evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight),
    )
    .toBeLessThan(3);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/interview-conversation-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page
    .getByRole("button", { name: "Save conversation for review" })
    .click();
  await expect(
    page.getByText("Review the conversation", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Edit transcript turn" }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Start to review interview", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`/interview-studio/${sid}/review$`));
  await expect(
    page.getByRole("heading", { name: "Review your interview", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("log", { name: "Interview conversation" }),
  ).toHaveCSS("max-height", "none");
  await page
    .getByRole("button", { name: "Edit transcript turn" })
    .nth(1)
    .click();
  await page
    .getByLabel("Corrected text for turn 2")
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
