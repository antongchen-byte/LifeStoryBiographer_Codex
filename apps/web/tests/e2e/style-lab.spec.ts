import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";

function syntheticWav() {
  const samples = 8 * 8000;
  const buffer = Buffer.alloc(44 + samples * 2);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(buffer.length - 8, 4);
  buffer.write("WAVEfmt ", 8);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(8000, 24);
  buffer.writeUInt32LE(16000, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(samples * 2, 40);
  for (let i = 0; i < samples; i++)
    buffer.writeInt16LE(
      Math.round(Math.sin((i / 8000) * 440 * Math.PI * 2) * 2000),
      44 + i * 2,
    );
  return buffer;
}

test("review recording evidence, publish a style, and preserve its snapshot after correction", async ({
  page,
}) => {
  page.setDefaultTimeout(15000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/login");
  await page
    .getByRole("button", { name: "Create an account", exact: true })
    .click();
  await page.getByLabel("Your name").fill("Style Lab Tester");
  await page
    .getByLabel("Email address")
    .fill(`style-${Date.now()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-browser-password");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "My biographies" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "New biography" }).click();
  await page.getByLabel("Subject’s name").fill("Style Lab Fixture");
  await page.getByLabel("Biography title").fill("Learning to listen");
  await page
    .getByRole("button", { name: "Create biography", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Learning to listen" }),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: /Style Lab/ })
    .click();
  await page
    .getByLabel("Profile name", { exact: true })
    .fill("A thoughtful interviewer");
  await page
    .getByRole("combobox", { name: "Biography workspace", exact: true })
    .selectOption({ label: "Learning to listen" });
  await page
    .getByRole("button", { name: "Create profile", exact: true })
    .click();
  await expect(
    page.getByRole("combobox", { name: "Interviewer profile", exact: true }),
  ).toBeVisible();
  const profileId = await page
    .getByRole("combobox", { name: "Interviewer profile", exact: true })
    .inputValue();
  const profile = await (
    await page.request.get(`/api/backend/profiles/${profileId}`)
  ).json();
  const projectId = profile.project_id;
  const origin = { Origin: "http://localhost:3000" };
  try {
    await page
      .getByRole("button", { name: "Upload recordings", exact: true })
      .click();
    await page.locator(".consent input").check();
    await page.getByLabel("Upload files").setInputFiles({
      name: "synthetic-interview.wav",
      mimeType: "audio/wav",
      buffer: syntheticWav(),
    });
    const recording = page.getByRole("button").filter({
      has: page.getByRole("heading", {
        name: "synthetic-interview.wav",
        exact: true,
      }),
    });
    await expect(recording).toContainText("Ready", { timeout: 90000 });
    await page
      .getByRole("combobox", { name: "Available recordings", exact: true })
      .selectOption({ label: "synthetic-interview.wav" });
    await page
      .getByRole("button", { name: "Add recording", exact: true })
      .click();
    await expect(page.locator(".style-source")).toContainText(
      "synthetic-interview.wav",
    );
    await page
      .locator(".style-source")
      .getByRole("button", { name: "Transcript workspace", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Listen to the recording", exact: true })
      .click();
    await expect(page.locator(".style-player audio")).toBeVisible();
    await expect
      .poll(() =>
        page
          .locator(".style-player audio")
          .evaluate((a) => (a as HTMLAudioElement).duration),
      )
      .toBeGreaterThan(7);
    for (const t of [
      {
        role: "interviewer",
        start: "0",
        end: "2",
        text: "Can you describe a particular moment?",
      },
      {
        role: "participant",
        start: "2",
        end: "4",
        text: "I remember a conversation during a journey.",
      },
    ]) {
      await page
        .getByRole("button", {
          name: "Add transcript turn manually",
          exact: true,
        })
        .click();
      await page
        .getByRole("textbox", { name: "Speaker label", exact: true })
        .fill(t.role === "interviewer" ? "Speaker A" : "Speaker B");
      await page
        .getByRole("combobox", { name: "Speaker role", exact: true })
        .selectOption(t.role);
      await page.getByLabel("Start (seconds)", { exact: true }).fill(t.start);
      await page.getByLabel("End (seconds)", { exact: true }).fill(t.end);
      await page
        .getByRole("textbox", { name: "Transcript text", exact: true })
        .fill(t.text);
      await page
        .getByRole("button", { name: "Save transcript turn", exact: true })
        .click();
      await expect(
        page.locator(".style-turn").filter({ hasText: t.text }),
      ).toBeVisible();
    }
    // Give both turns the same verified label, then exercise default and local scopes.
    const sourceId = page.url().split("/").pop();
    const turnsUrl = `/api/backend/profiles/${profileId}/sources/${sourceId}/turns`;
    const beforeRoles = (await (await page.request.get(turnsUrl)).json()).items;
    const secondTurn = beforeRoles[1];
    expect(
      (
        await page.request.patch(`${turnsUrl}/${secondTurn.id}`, {
          headers: origin,
          data: {
            speaker: "Speaker A",
            role: secondTurn.role,
            start_ms: secondTurn.start_ms,
            end_ms: secondTurn.end_ms,
            text: secondTurn.text,
          },
        })
      ).status(),
    ).toBe(200);
    await page.reload();
    const roleCards = page.locator(".style-turn");
    await roleCards
      .first()
      .getByRole("button", { name: "Edit words & role" })
      .click();
    await expect(
      page.getByLabel("Apply role to all turns with this speaker label", {
        exact: true,
      }),
    ).toBeChecked();
    await page
      .getByRole("combobox", { name: "Speaker role", exact: true })
      .selectOption("other");
    await page
      .getByRole("button", { name: "Save transcript turn", exact: true })
      .click();
    await expect(roleCards.locator(".status-pill")).toHaveText([
      "other",
      "other",
    ]);
    await roleCards
      .nth(1)
      .getByRole("button", { name: "Edit words & role" })
      .click();
    await page
      .getByLabel("Apply role to all turns with this speaker label", {
        exact: true,
      })
      .uncheck();
    await page
      .getByRole("combobox", { name: "Speaker role", exact: true })
      .selectOption("participant");
    await page
      .getByRole("button", { name: "Save transcript turn", exact: true })
      .click();
    await expect(roleCards.nth(1).locator(".status-pill")).toHaveText(
      "participant · local override",
    );
    await roleCards
      .first()
      .getByRole("button", { name: "Edit words & role" })
      .click();
    await page
      .getByRole("combobox", { name: "Speaker role", exact: true })
      .selectOption("interviewer");
    await page
      .getByRole("button", { name: "Save transcript turn", exact: true })
      .click();
    await expect(roleCards.locator(".status-pill")).toHaveText([
      "interviewer",
      "participant · local override",
    ]);
    // One recording-wide panel plus a direct sentence menu.
    await expect(
      page.getByRole("region", { name: "Speaker roles", exact: true }),
    ).toHaveCount(1);
    await page
      .getByRole("combobox", {
        name: "Default role for speaker A",
        exact: true,
      })
      .selectOption("other");
    await expect(roleCards.locator(".status-pill")).toHaveText([
      "other",
      "participant · local override",
    ]);
    await page
      .getByRole("combobox", {
        name: "Default role for speaker A",
        exact: true,
      })
      .selectOption("interviewer");
    await roleCards.nth(1).getByRole("combobox").selectOption("other");
    await expect(roleCards.nth(1).locator(".status-pill")).toHaveText(
      "other · local override",
    );
    await roleCards.nth(1).getByRole("combobox").selectOption("participant");
    await expect(roleCards.nth(1).locator(".status-pill")).toHaveText(
      "participant · local override",
    );
    // The native picker is substituted; API, versioning, search and UI use the real stack.
    await page.evaluate(() => {
      const files: Record<string, string> = {};
      Object.assign(window, {
        archiveFiles: files,
        pickerMode: "cancel",
        showDirectoryPicker: async () => {
          const mode = (window as unknown as { pickerMode: string }).pickerMode;
          if (mode === "cancel")
            throw new DOMException("Cancelled", "AbortError");
          return {
            name: "Test scripts",
            getFileHandle: async (name: string) => ({
              createWritable: async () => ({
                write: async (value: string) => {
                  if (mode === "fail")
                    throw new Error("Synthetic disk failure");
                  files[name] = value;
                },
                close: async () => {},
                abort: async () => {},
              }),
              getFile: async () => new File([files[name]], name),
            }),
          };
        },
      });
    });
    const approve = page.getByRole("button", {
      name: "Approve & save to local folder",
      exact: true,
    });
    await approve.click();
    await expect(page.locator("p[role=alert]")).toContainText(
      "Folder selection cancelled",
    );
    await page.evaluate(() => Object.assign(window, { pickerMode: "fail" }));
    await approve.click();
    await expect(page.locator("p[role=alert]")).toContainText(
      "Synthetic disk failure",
    );
    await page.reload();
    await expect(
      page.getByText("Approved · local save not confirmed · not indexed", {
        exact: true,
      }),
    ).toBeVisible();
    // Reinstall the simulated directory after reload to verify recovery.
    await page.evaluate(() => {
      const files: Record<string, string> = {};
      Object.assign(window, {
        archiveFiles: files,
        showDirectoryPicker: async () => ({
          name: "Test scripts",
          getFileHandle: async (name: string) => ({
            createWritable: async () => ({
              write: async (value: string) => {
                files[name] = value;
              },
              close: async () => {},
              abort: async () => {},
            }),
            getFile: async () => new File([files[name]], name),
          }),
        }),
      });
    });
    await page
      .getByRole("button", { name: "Retry local save", exact: true })
      .click();
    await expect(page.locator(".style-notice[role=status]")).toContainText(
      "added to searchable memory",
    );
    const files = await page.evaluate(
      () =>
        (window as unknown as { archiveFiles: Record<string, string> })
          .archiveFiles,
    );
    expect(Object.keys(files).length).toBe(2);
    expect(
      Object.values(files).every((v) =>
        v.includes("conversation during a journey"),
      ),
    ).toBe(true);
    await page.getByLabel("Words to find", { exact: true }).fill("journey");
    await page.getByRole("button", { name: "Search saved scripts" }).click();
    await expect(page.locator("article")).toContainText(
      "conversation during a journey",
    );
    await page
      .getByRole("button", { name: "View saved script", exact: true })
      .click();
    await expect(page.locator("pre")).toContainText(
      "Can you describe a particular moment?",
    );
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await mkdir("/private/tmp/lifestory-previews", { recursive: true });
    await page.screenshot({
      path: "/private/tmp/lifestory-previews/script-review-mobile.png",
      fullPage: true,
    });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page
      .getByRole("link", { name: "Back to Style Lab", exact: false })
      .click();
    await page.getByRole("button", { name: /2\. Transcript evidence/ }).click();
    for (const checkbox of await page
      .locator(".style-evidence-check input")
      .all())
      await checkbox.check();
    await page
      .getByRole("button", { name: "Create pattern from selection" })
      .click();
    await page
      .getByLabel("Reusable style instruction")
      .fill("Invite a specific memory when an answer is abstract.");
    await page
      .getByLabel("Anonymized example")
      .fill("Can you take me back to one particular moment?");
    await expect(
      page.getByRole("button", { name: "Approve pattern", exact: true }),
    ).toBeDisabled();
    await page.getByLabel("I checked the evidence", { exact: false }).check();
    await page
      .getByRole("button", { name: "Approve pattern", exact: true })
      .click();
    await expect(page.locator(".style-pattern")).toContainText("approved");
    await mkdir("/private/tmp/lifestory-previews", { recursive: true });
    await page.screenshot({
      path: "/private/tmp/lifestory-previews/style-lab.png",
      fullPage: true,
    });
    await page.getByRole("button", { name: /4\. Publish/ }).click();
    await page
      .getByRole("button", { name: "Publish style version", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Version 1", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: /2\. Transcript evidence/ }).click();
    await page
      .locator(".style-turn")
      .first()
      .getByRole("button", { name: "Edit words & role" })
      .click();
    await page
      .getByRole("textbox", { name: "Transcript text", exact: true })
      .fill("A corrected question in the working transcript.");
    await page
      .getByRole("button", { name: "Save transcript turn", exact: true })
      .click();
    await expect(
      page.getByText("Review required", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: /3\. Style & examples/ }).click();
    await expect(page.locator(".style-pattern")).toContainText("pending");
    await page.getByRole("button", { name: /4\. Publish/ }).click();
    await page
      .getByRole("button", { name: "View snapshot", exact: true })
      .click();
    await page.getByText("Frozen evidence · 2 turns", { exact: true }).click();
    await expect(page.locator(".style-snapshot")).toContainText(
      "Can you describe a particular moment?",
    );
    await expect(
      page.getByText("Awaiting reference questions", { exact: true }),
    ).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: "/private/tmp/lifestory-previews/style-lab-mobile.png",
      fullPage: true,
    });
    await page.reload();
    await expect(
      page.getByRole("combobox", { name: "Interviewer profile", exact: true }),
    ).toHaveValue(profileId);
    await page.goto(`/style-lab/${profileId}/scripts/${sourceId}`);
    await expect(page.locator(".style-turn")).toHaveCount(2);
    page.once("dialog", (dialog) => dialog.dismiss());
    await page
      .getByRole("button", { name: "Delete script", exact: true })
      .click();
    await expect(page.locator(".style-turn")).toHaveCount(2);
    page.once("dialog", (dialog) => dialog.accept());
    await page
      .getByRole("button", { name: "Delete script", exact: true })
      .click();
    await expect(page.locator(".style-turn")).toHaveCount(0);
    await expect(
      page.getByText("No approved versions yet.", { exact: true }),
    ).toBeVisible();
    const cleared = await (
      await page.request.get(`/api/backend/profiles/${profileId}`)
    ).json();
    expect(cleared.sources).toHaveLength(1);
    expect(cleared.sources[0].turn_count).toBe(0);
    expect(cleared.patterns).toHaveLength(0);
    expect(cleared.versions).toHaveLength(0);
    expect(
      (
        await (
          await page.request.get(
            `/api/backend/profiles/${profileId}/memory?q=journey`,
          )
        ).json()
      ).items,
    ).toHaveLength(0);
    expect(errors).toEqual([]);
  } finally {
    expect(
      (
        await page.request.delete(`/api/backend/profiles/${profileId}`, {
          headers: origin,
        })
      ).status(),
    ).toBe(204);
    const media = await (
      await page.request.get(`/api/backend/projects/${projectId}/media`)
    ).json();
    for (const a of media)
      expect(
        (
          await page.request.delete(
            `/api/backend/projects/${projectId}/media/${a.id}`,
            { headers: origin },
          )
        ).status(),
      ).toBe(204);
    expect(
      (
        await page.request.delete(`/api/backend/projects/${projectId}`, {
          headers: origin,
        })
      ).status(),
    ).toBe(204);
  }
});
