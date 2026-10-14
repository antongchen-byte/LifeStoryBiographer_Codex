import { test, expect } from "@playwright/test";
import { readFile, mkdir } from "node:fs/promises";

test("Cinema generation, review, continuity and final save", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/login");
  await page
    .getByRole("button", { name: "Create an account", exact: true })
    .click();
  await page.getByLabel("Your name").fill("Cinema tester");
  await page
    .getByLabel("Email address")
    .fill(`cinema-${Date.now()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-cinema-password");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "My biographies" }),
  ).toBeVisible();
  const proxy = await page.request.get("/api/backend/cinema/nonexistent");
  expect((await proxy.json()).detail).toBe("Cinema production not found");
  const video = await readFile("/private/tmp/lifestory-cinema-sample.mp4");
  await page.route("**/cinema-fixture.mp4*", (route) =>
    route.fulfill({ contentType: "video/mp4", body: video }),
  );
  const p: any = {
    id: "production-fixture",
    screenplay_id: "screenplay-fixture",
    revision: 4,
    interview_uid: "interview-fixture",
    title: "Garden film",
    all_approved: false,
    materials: [],
    renders: [],
    units: [1, 2].map((n) => ({
      id: `unit-${n}`,
      position: n,
      section_position: 1,
      seconds: 10,
      prompt: `A gardener walks through gate ${n}.`,
      stale: false,
      clip: null,
      content: {
        material_ids: [],
        elements: [{ kind: "scene", text: "EXT. GARDEN - DAY" }],
      },
    })),
  };
  let count = 0;
  const submissions: any[] = [];
  await page.route("**/api/backend/interviews/screenplays", (route) =>
    route.fulfill({
      json: [{ id: p.screenplay_id, title: p.title, revision: 4 }],
    }),
  );
  await page.route("**/api/backend/cinema/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/generate")) {
      const body = route.request().postDataJSON();
      submissions.push(body);
      const unit = p.units.find((u: any) =>
        path.includes(`/subsections/${u.id}/`),
      );
      unit.clip = {
        id: `clip-${++count}`,
        kind: "clip",
        state: "ready",
        approved: false,
        frame_ready: true,
        previewed: false,
        request: {
          ...body,
          previous_id: body.previous_frame ? p.units[0].clip.id : null,
        },
        duration: 1,
        preview_url: `/cinema-fixture.mp4?v=${count}`,
        download_url: "/cinema-fixture.mp4",
        error: null,
      };
    } else if (path.endsWith("/previewed")) {
      p.units.find((u: any) =>
        path.includes(`/clips/${u.clip?.id}/`),
      ).clip.previewed = true;
      await route.fulfill({ json: { previewed: true } });
      return;
    } else if (path.endsWith("/review")) {
      p.units.find((u: any) =>
        path.includes(`/clips/${u.clip?.id}/`),
      ).clip.approved = route.request().postDataJSON().approved;
    } else if (path.includes("/renders/")) {
      const kind = path.split("/").at(-1);
      p.renders.push({
        id: `render-${kind}`,
        kind,
        state: "ready",
        request: {},
        preview_url: "/cinema-fixture.mp4",
        download_url: "/cinema-fixture.mp4",
      });
    }
    p.all_approved = p.units.every((u: any) => u.clip?.approved);
    await route.fulfill({ json: p });
  });
  await page.goto("/cinema-studio?screenplay=screenplay-fixture");
  await expect(page.getByLabel("Choose your screenplay")).toHaveValue(
    "screenplay-fixture",
  );
  await expect(
    page.getByRole("heading", { name: "Garden film" }),
  ).toBeVisible();
  const cards = page.locator(".cinema-clip");
  await expect(
    cards
      .first()
      .getByRole("button", { name: "Generate video clip", exact: true }),
  ).toBeDisabled();
  await page.getByRole("checkbox", { name: /I agree to send/ }).check();
  await cards
    .first()
    .getByLabel("Consistent character and environment descriptions")
    .fill("A gardener in a blue coat beside a brick wall.");
  await cards
    .first()
    .getByRole("button", { name: "Generate video clip", exact: true })
    .click();
  await expect(
    cards.first().getByRole("button", { name: "Yes, satisfied" }),
  ).toHaveCount(0);
  await cards
    .first()
    .locator("video")
    .evaluate((v: HTMLVideoElement) => v.play());
  await cards
    .nth(1)
    .getByRole("checkbox", { name: "Start from last frame of previous clip" })
    .check();
  await expect(
    cards
      .nth(1)
      .getByLabel("Consistent character and environment descriptions"),
  ).toHaveValue("A gardener in a blue coat beside a brick wall.");
  await cards
    .nth(1)
    .getByRole("button", { name: "Generate video clip", exact: true })
    .click();
  expect(submissions[1].previous_frame).toBe(true);
  await cards.first().getByRole("button", { name: "Yes, satisfied" }).click();

  await cards
    .nth(1)
    .locator("video")
    .evaluate((v: HTMLVideoElement) => v.play());
  await cards
    .nth(1)
    .getByRole("button", { name: "No, revise this clip" })
    .click();
  await cards
    .nth(1)
    .getByLabel("Video prompt for subsection 1.2")
    .fill("Unsaved changed prompt");
  await cards
    .nth(1)
    .getByRole("button", { name: "Regenerate with the same prompt" })
    .click();
  expect(submissions[2].prompt).toBe(submissions[1].prompt);
  await expect(cards.nth(1).locator("video")).toHaveAttribute(
    "src",
    "/cinema-fixture.mp4?v=3",
  );
  await expect(
    cards.nth(1).getByRole("button", { name: "Generate revised clip" }),
  ).toBeEnabled();
  await cards
    .nth(1)
    .locator("video")
    .evaluate((v: HTMLVideoElement) => v.play());
  await cards.nth(1).getByRole("button", { name: "Yes, satisfied" }).click();
  await page
    .getByRole("button", {
      name: "Save approved clips to database and archive",
    })
    .click();
  await expect(
    page.getByRole("link", { name: "Download all clips (ZIP)" }),
  ).toBeVisible();
  await page.evaluate(() => {
    const target = window as any;
    target.savedCinemaFiles = [];
    const directory = {
      getDirectoryHandle: async () => directory,
      getFileHandle: async (name: string) => ({
        createWritable: async () => ({
          write: async () => {
            target.savedCinemaFiles.push(name);
          },
          close: async () => {},
        }),
      }),
    };
    target.showDirectoryPicker = async () => directory;
  });
  await page
    .getByRole("button", { name: "Save clips to a local folder" })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Approved clips saved to your selected folder",
  );
  expect(
    await page.evaluate(() => (window as any).savedCinemaFiles.length),
  ).toBe(3);
  await page.getByRole("button", { name: "Yes, stitch clips" }).click();
  await expect(
    page.getByRole("link", { name: "Download stitched film" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "All clips approved" }),
  ).toBeVisible();
  await mkdir("/private/tmp/lifestory-previews", { recursive: true });
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/cinema-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/cinema-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
