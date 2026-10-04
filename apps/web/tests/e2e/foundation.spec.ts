import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";

test("create an account, a biography, and a processed memory", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/login");
  await page
    .getByRole("button", { name: "Create an account", exact: true })
    .click();
  await page.getByLabel("Your name").fill("Browser Test Author");
  await page
    .getByLabel("Email address")
    .fill(`browser-${Date.now()}@example.com`);
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
  await page.getByLabel("Subject’s name").fill("Elena Martin");
  await page.getByLabel("Biography title").fill("A life of small adventures");
  await page
    .getByRole("button", { name: "Create biography", exact: true })
    .click();
  const card = page.getByRole("link").filter({
    has: page.getByRole("heading", { name: "A life of small adventures" }),
  });
  await expect(card).toBeVisible();
  await mkdir("/private/tmp/lifestory-previews", { recursive: true });
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/dashboard.png",
    fullPage: true,
  });
  await card.click();
  await page.waitForURL(/\/projects\/[a-f0-9-]+$/);
  await expect(
    page.getByRole("heading", { name: "A life of small adventures" }),
  ).toBeVisible();
  const project = page.url().split("/").pop();
  await page.getByRole("checkbox").check();
  const jpeg = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 640;
    canvas.height = 400;
    const context = canvas.getContext("2d")!;
    context.fillStyle = "#cbd6b5";
    context.fillRect(0, 0, 640, 400);
    context.fillStyle = "#7f9572";
    context.fillRect(0, 220, 640, 180);
    context.fillStyle = "#fff3c9";
    context.beginPath();
    context.arc(480, 90, 35, 0, Math.PI * 2);
    context.fill();
    return canvas.toDataURL("image/jpeg").split(",")[1];
  });
  await page.getByLabel("Upload files").setInputFiles({
    name: "a-summer-memory.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from(jpeg, "base64"),
  });
  const photo = page.getByRole("button").filter({
    has: page.getByRole("heading", { name: "a-summer-memory.jpg" }),
  });
  await expect(photo).toContainText("Ready", { timeout: 90000 });
  page.once("dialog", async (dialog) => {
    expect(dialog.message()).toContain("Possible duplicate");
    expect(dialog.message()).toContain("A life of small adventures");
    await dialog.dismiss();
  });
  await page.getByLabel("Upload files").setInputFiles({
    name: "a-summer-memory.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from(jpeg, "base64"),
  });
  await expect(
    page.getByText("Duplicate files skipped. No new copies were uploaded.", {
      exact: true,
    }),
  ).toBeVisible();
  expect(
    (
      await (
        await page.request.get(`/api/backend/projects/${project}/media`)
      ).json()
    ).length,
  ).toBe(1);
  await photo.click();
  await expect(page.locator(".media-preview img")).toBeVisible();
  await expect
    .poll(() =>
      page
        .locator(".media-preview img")
        .evaluate((img) => (img as HTMLImageElement).naturalWidth),
    )
    .toBe(640);
  await page.getByRole("button", { name: "Close media" }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByLabel("Upload files").setInputFiles({
    name: "a-summer-memory.jpg",
    mimeType: "image/jpeg",
    buffer: Buffer.from(jpeg, "base64"),
  });
  await expect(photo).toHaveCount(2);
  await expect(photo.nth(1)).toContainText("Ready", { timeout: 90000 });

  await page.getByLabel("Upload files").setInputFiles({
    name: "a-small-memory.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "A synthetic memory created by the browser acceptance test.\n",
    ),
  });
  const asset = page
    .getByRole("button")
    .filter({ has: page.getByRole("heading", { name: "a-small-memory.txt" }) });
  await expect(asset).toContainText("Ready", { timeout: 90000 });
  await asset.click();
  await page
    .getByLabel("The story behind this memory")
    .fill("A note with a date and a place, preserved for later.");
  await page.getByRole("button", { name: "Save note" }).click();
  await page.getByRole("button", { name: "Close media" }).click();
  await page.reload();
  await expect(asset).toBeVisible();
  await asset.click();
  await expect(page.getByLabel("The story behind this memory")).toHaveValue(
    "A note with a date and a place, preserved for later.",
  );
  await page.getByRole("button", { name: "Close media" }).click();
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/media-library.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "A life of small adventures" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "/private/tmp/lifestory-previews/mobile.png",
    fullPage: true,
  });
  await page
    .getByLabel("I own these files or have permission to use them.")
    .check();
  // Verify the browser accepts recording metadata above 2 GiB without transferring gigabytes.
  let largeRecordingSize = 0;
  await page.route("**/media/uploads", async (route) => {
    const body = route.request().postDataJSON();
    if (body.filename !== "large-recording.mp4") return route.continue();
    largeRecordingSize = body.size_bytes;
    await route.fulfill({
      status: 201,
      json: {
        asset_id: "synthetic-large-recording",
        status: "uploaded",
        part_size: 8388608,
        part_urls: [],
        uploaded_parts: [],
      },
    });
  });
  await page.evaluate(() => {
    const size = Object.getOwnPropertyDescriptor(Blob.prototype, "size")!.get!;
    Object.defineProperty(File.prototype, "size", {
      configurable: true,
      get() {
        return this.name === "large-recording.mp4"
          ? 3 * 1024 ** 3
          : size.call(this);
      },
    });
  });
  await page.getByLabel("Upload files").setInputFiles({
    name: "large-recording.mp4",
    mimeType: "video/mp4",
    buffer: Buffer.from("synthetic size-only fixture"),
  });
  await expect.poll(() => largeRecordingSize).toBe(3 * 1024 ** 3);
  await page.evaluate(() => {
    Reflect.deleteProperty(File.prototype, "size");
  });
  const media = await (
    await page.request.get(`/api/backend/projects/${project}/media`)
  ).json();
  for (const item of media) {
    const response = await page.request.delete(
      `/api/backend/projects/${project}/media/${item.id}`,
      { headers: { Origin: "http://localhost:3000" } },
    );
    expect(response.status()).toBe(204);
  }
  const deleted = await page.request.delete(
    `/api/backend/projects/${project}`,
    { headers: { Origin: "http://localhost:3000" } },
  );
  expect(deleted.status()).toBe(204);
  const session = await (await page.request.get("/api/auth/session")).text();
  expect(session).not.toContain("backendToken");
  expect(errors).toEqual([]);
});
