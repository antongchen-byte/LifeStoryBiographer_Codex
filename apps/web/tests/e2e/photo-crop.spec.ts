import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";

test("crop uploaded photo at native resolution and resize a separate copy", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/login");
  await page
    .getByRole("button", { name: "Create an account", exact: true })
    .click();
  await page.getByLabel("Your name").fill("Crop tester");
  await page.getByLabel("Email address").fill(`crop-${Date.now()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("synthetic-crop-password");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "My biographies" }),
  ).toBeVisible();
  const response = await page.request.post("/api/backend/projects", {
    headers: { Origin: "http://localhost:3000" },
    data: { subject_name: "Crop fixture", title: "Crop fixture" },
  });
  expect(response.ok()).toBeTruthy();
  const project = (await response.json()).id;
  await page.goto(`/projects/${project}`);
  await page.getByRole("checkbox").check();
  const photo = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 1600;
    canvas.height = 1200;
    const c = canvas.getContext("2d")!;
    c.fillStyle = "#b2c4aa";
    c.fillRect(0, 0, 1600, 1200);
    c.fillStyle = "#526c45";
    c.fillRect(0, 600, 1600, 600);
    c.fillStyle = "#ffdb68";
    c.beginPath();
    c.arc(1150, 300, 100, 0, Math.PI * 2);
    c.fill();
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page
    .getByLabel("Upload files")
    .setInputFiles({
      name: "garden-photo.png",
      mimeType: "image/png",
      buffer: Buffer.from(photo, "base64"),
    });
  const card = page
    .getByRole("button")
    .filter({
      has: page.getByRole("heading", { name: "garden-photo.png", exact: true }),
    });
  await expect(card).toContainText("Ready", { timeout: 90000 });
  await card.click();
  await page.getByRole("button", { name: "Crop / resize to 16:9" }).click();
  const editor = page.getByRole("dialog", {
    name: "Crop garden-photo.png to 16:9",
  });
  await expect(editor.getByLabel("Output size")).toHaveValue("original");
  await expect(
    editor.getByText(
      "Saved image: 1600 × 900 pixels. The preview is scaled to fit.",
    ),
  ).toBeVisible();
  await editor.getByLabel("Zoom", { exact: true }).fill("2");
  await editor.getByLabel("Vertical position").fill("1");
  await expect(
    editor.getByText(
      "Saved image: 800 × 450 pixels. The preview is scaled to fit.",
    ),
  ).toBeVisible();
  await mkdir("/private/tmp/lifestory-previews", { recursive: true });
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/photo-crop-desktop.png",
  });
  await editor.getByRole("button", { name: "Save cropped copy" }).click();
  await expect(
    editor.getByRole("link", { name: "Download cropped photo" }),
  ).toBeVisible();
  let media = await (
    await page.request.get(`/api/backend/projects/${project}/media`)
  ).json();
  expect(media).toHaveLength(2);
  expect(
    media.find((m: any) => m.original_filename === "garden-photo.png").width,
  ).toBe(1600);
  expect(media.find((m: any) => m.details.crop).width).toBe(800);
  expect(media.find((m: any) => m.details.crop).height).toBe(450);
  await editor.getByLabel("Output size").selectOption("720p");
  await editor.getByRole("button", { name: "Save cropped copy" }).click();
  await expect(editor.getByRole("status")).toContainText("1280 × 720");
  media = await (
    await page.request.get(`/api/backend/projects/${project}/media`)
  ).json();
  expect(media).toHaveLength(3);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/photo-crop-mobile.png",
  });
  expect(await editor.evaluate((e) => e.scrollWidth <= e.clientWidth + 1)).toBe(
    true,
  );
  await editor.getByRole("button", { name: "Close crop editor" }).click();
  await page.getByRole("button", { name: "Close media" }).click();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: /garden-photo-16x9/ }),
  ).toHaveCount(2);
  await card.click();
  await page.getByRole("button", {name: "Remove sensitive text", exact: true}).click();
  const redactor = page.getByRole("dialog", {name: "Remove text from garden-photo.png"});
  const canvas = redactor.getByLabel("Mark sensitive text areas");
  await expect(canvas).toBeVisible();
  const bounds = (await canvas.boundingBox())!;
  await page.mouse.move(bounds.x + bounds.width * .1, bounds.y + bounds.height * .1);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width * .4, bounds.y + bounds.height * .4);
  await page.mouse.up();
  await expect(redactor.getByText("1 areas marked. Original resolution is preserved.")).toBeVisible();
  await redactor.getByRole("button", {name: "Save text-removed copy"}).click();
  await expect(redactor.getByRole("link", {name: "Download text-removed photo"})).toBeVisible();
  const updated = await (await page.request.get(`/api/backend/projects/${project}/media`)).json();
  const redacted = updated.find((m: any) => m.original_filename.includes("text-removed"));
  expect([redacted.width, redacted.height]).toEqual([1600,1200]);
  expect(errors).toEqual([]);
});
