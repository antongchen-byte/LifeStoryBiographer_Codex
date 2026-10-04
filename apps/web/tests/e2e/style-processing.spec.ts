import { test, expect } from "@playwright/test";

test("uploaded recording has start action, saved progress, and a transcript destination", async ({
  page,
}) => {
  let phase = "idle";
  let configured = false;
  let attached = false;
  let deleted = false;
  const source = {
    id: "source",
    asset_id: "asset",
    filename: "long-interview.mp4",
    mime_type: "video/mp4",
    duration_ms: 60000,
    reviewed: false,
    revision: 1,
    turn_count: phase === "completed" ? 1 : 0,
  };
  await page.route("**/api/auth/session", (r) =>
    r.fulfill({
      json: {
        user: { name: "Flow test", email: "flow@example.com" },
        expires: "2099-01-01T00:00:00Z",
      },
    }),
  );
  await page.route("**/api/backend/**", async (r) => {
    const path = new URL(r.request().url()).pathname.replace(
      "/api/backend",
      "",
    );
    if (path.endsWith("/speakers") && r.request().method() === "GET")
      return r.fulfill({
        json: { items: [], unassigned: 0, missing_roles: [] },
      });
    if (path === "/profiles")
      return r.fulfill({
        json: [
          {
            id: "profile",
            name: "Interview style",
            project_id: "project",
            description: "",
          },
        ],
      });
    if (path === "/projects")
      return r.fulfill({
        json: [
          {
            id: "project",
            title: "Interviews",
            role: "OWNER",
            subject_name: "Test",
          },
        ],
      });
    if (path === "/projects/project/media" && deleted)
      return r.fulfill({ json: [] });
    if (path === "/jobs/job" && r.request().method() === "DELETE") {
      phase = "idle";
      return r.fulfill({ status: 204 });
    }
    if (path.endsWith("/archives") && r.request().method() === "GET")
      return r.fulfill({ json: [] });
    if (path === "/jobs/job/stop") {
      phase = "stopping";
      return r.fulfill({ status: 202, json: { state: phase } });
    }
    if (path === "/jobs/job/retry") {
      phase = "running";
      return r.fulfill({ status: 202, json: { state: phase } });
    }
    if (
      path === "/profiles/profile/sources/source" &&
      r.request().method() === "DELETE"
    ) {
      deleted = true;
      attached = false;
      phase = "idle";
      return r.fulfill({ status: 204 });
    }
    if (path === "/projects/project/media")
      return r.fulfill({
        json: [
          {
            id: "asset",
            original_filename: source.filename,
            mime_type: source.mime_type,
            status: "ready",
            size_bytes: 100,
            duration_ms: 60000,
          },
        ],
      });
    if (path === "/profiles/profile/assets") {
      attached = true;
      return r.fulfill({ status: 201, json: { id: "source" } });
    }
    if (path.endsWith("/transcribe")) {
      expect(r.request().postDataJSON().provider_consent).toBe(true);
      expect(attached).toBe(true);
      phase = "running";
      return r.fulfill({ status: 202, json: { id: "job" } });
    }
    if (path.endsWith("/turns"))
      return r.fulfill({
        json: {
          total: 1,
          items: [
            {
              id: "turn",
              source_id: "source",
              speaker: "1: A",
              role: "unknown",
              start_ms: 0,
              end_ms: 2000,
              text: "A fixture transcript ready for review.",
            },
          ],
        },
      });
    if (path === "/profiles/profile")
      return r.fulfill({
        json: {
          id: "profile",
          project_id: "project",
          name: "Interview style",
          description: "",
          provider_ready: configured,
          sources: attached
            ? [{ ...source, turn_count: phase === "completed" ? 1 : 0 }]
            : [],
          patterns: [],
          versions: [],
          jobs:
            phase === "idle"
              ? []
              : [
                  {
                    id: "job",
                    source_id: "source",
                    kind: "transcribe",
                    state: phase,
                    completed: phase === "completed" ? 2 : 1,
                    total: 2,
                    error: null,
                  },
                ],
        },
      });
    return r.fulfill({
      status: 404,
      json: { detail: "Unexpected fixture endpoint" },
    });
  });
  await page.goto("/style-lab");
  const card = page.locator(".style-recording-action");
  await expect(
    card.getByRole("button", { name: "Create transcript", exact: true }),
  ).toBeVisible();
  await expect(
    card.getByRole("button", { name: "Create transcript", exact: true }),
  ).toBeDisabled();
  await expect(page.getByText(/Transcription setup required:/)).toBeVisible();
  configured = true;
  await page.reload();
  await page
    .getByLabel("I authorize sending these recordings", { exact: false })
    .check();
  await card
    .getByRole("button", { name: "Create transcript", exact: true })
    .click();
  await expect(
    page.getByRole("progressbar", { name: "Processing progress" }),
  ).toHaveAttribute("value", "50");
  await expect(page.getByText(/Transcribing · 50%/)).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("progressbar", { name: "Processing progress" }),
  ).toHaveAttribute("value", "50");
  await expect(
    card.getByRole("button", { name: "Delete recording" }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Stop processing", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Stopping…", exact: true }),
  ).toBeDisabled();
  phase = "cancelled";
  await expect(
    page.getByRole("button", { name: "Resume processing", exact: true }),
  ).toBeEnabled({ timeout: 10000 });
  await expect(
    page.getByText("Stopped — saved sections retained", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Resume processing", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Stop processing", exact: true }),
  ).toBeVisible();
  phase = "completed";
  await expect(
    page.getByText("Processing complete · 100%", { exact: false }),
  ).toBeVisible({ timeout: 10000 });
  await expect(
    page.getByRole("progressbar", { name: "Processing progress" }),
  ).toHaveAttribute("value", "100");
  await page
    .locator(".style-job")
    .getByRole("button", { name: "Open transcript" })
    .click();
  await expect(
    page.getByText("A fixture transcript ready for review.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Edit words & role" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("link", { name: "Back to Style Lab", exact: false })
    .click();
  const deleteProcessing = page.getByRole("button", {
    name: "Delete processing & script",
    exact: true,
  });
  page.once("dialog", (dialog) => dialog.dismiss());
  await deleteProcessing.click();
  await expect(page.locator(".style-job")).toHaveCount(1);
  page.once("dialog", (dialog) => dialog.accept());
  await deleteProcessing.click();
  await expect(page.locator(".style-job")).toHaveCount(0);
  await expect(card).toBeVisible();
  page.once("dialog", (dialog) => dialog.dismiss());
  await card.getByRole("button", { name: "Delete recording" }).click();
  await expect(card).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await card.getByRole("button", { name: "Delete recording" }).click();
  await expect(card).toHaveCount(0);
  await expect(page.locator(".style-job")).toHaveCount(0);
});
