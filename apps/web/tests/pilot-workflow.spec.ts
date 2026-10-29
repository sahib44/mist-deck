import { test, expect } from "@playwright/test";

test("pilot folder tracks judge responses and creates separate sandbox messages", async ({ page }) => {
  page.on("dialog", (dialog) => dialog.accept());
  const password = process.env.SEED_PASSWORD;
  if (!password) throw new Error("SEED_PASSWORD is required");
  const title = `MIST-hack ${Date.now()}`;
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill("director@example.com");
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: "Competitions", exact: true }).click();
  await page.locator(".pilot-card").filter({ hasText: "Arts" }).click();
  await expect(page.getByRole("link", { name: /2D Art/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /3D Art/ })).toBeVisible();
  await page.getByRole("button", { name: "Add pilot competition" }).click();
  await expect(page.getByLabel("Competition name")).toHaveValue("");
  await expect(page.getByLabel("Event year")).toHaveValue("");
  await page.getByLabel("Competition name").fill(title);
  await page.getByLabel("Event year").fill("2027");
  await page.getByRole("button", { name: "Create pilot" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText("No rules uploaded yet.")).toBeVisible();
  await expect(page.getByText("No procedures uploaded yet.")).toBeVisible();

  for (const number of [1, 2, 3]) {
    await page.getByRole("button", { name: "Add judge" }).click();
    await page.getByLabel("Name", { exact: true }).fill(`Pilot Judge ${number}`);
    await page.getByLabel("Email", { exact: true }).fill(`pilot-judge-${number}@example.edu`);
    await page.getByLabel("Why this judge is qualified (optional)").fill("Experienced with software and engineering projects.");
    await page.getByRole("dialog").getByRole("button", { name: "Add judge" }).click();
    await expect(page.getByRole("dialog")).not.toBeVisible();
  }
  for (const number of [1, 2]) {
    const card = page.locator(".pilot-judge").filter({ hasText: `Pilot Judge ${number}` });
    await card.getByLabel("Response").selectOption("accepted");
  }
  await page.getByLabel("Response status").selectOption("accepted");
  await expect(page.locator(".pilot-judge")).toHaveCount(2);
  await page.locator(".pilot-summary button").filter({ hasText: "Accepted" }).click();
  await expect(page.locator(".pilot-judge")).toHaveCount(3);
  await page.locator(".pilot-judge").filter({ hasText: "Pilot Judge 3" }).getByLabel("Response").selectOption("accepted");
  await page.getByLabel("Response status").selectOption("accepted");
  await expect(page.locator(".pilot-judge")).toHaveCount(3);
  await page.getByLabel("Select visible judges").check();
  await expect(page.getByRole("button", { name: "Email selected (3)" })).toBeVisible();
  await page.getByRole("button", { name: "Email selected (3)" }).click();
  await expect(page.getByRole("heading", { name: `Compose for ${title}` })).toBeVisible();
  for (const number of [1, 2, 3]) {
    await expect(page.getByRole("button", { name: `Remove Pilot Judge ${number}`, exact: true })).toBeVisible();
  }
  await page.getByLabel("Campaign name").fill("Pilot judge update");
  await page.getByLabel("Attachments (optional; up to five files, 5 MB each)").setInputFiles({ name: "instructions.txt", mimeType: "text/plain", buffer: Buffer.from("Sample judging instructions") });
  await page.getByRole("button", { name: "Create draft & preview" }).click();
  await expect(page.getByRole("heading", { name: "Pilot judge update" })).toBeVisible();
  await expect(page.getByRole("link", { name: "instructions.txt" })).toBeVisible();
  await expect(page.getByText("3", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await page.getByRole("button", { name: "Approve campaign" }).click();
  await page.getByRole("button", { name: "Queue sandbox delivery" }).click();
  const campaignId = page.url().split("/campaigns/")[1];
  await expect.poll(async () => {
    const response = await page.request.get(`/api/outbox?campaign_id=${campaignId}`);
    const outbox = await response.json();
    return outbox.items.filter((item: any) => item.status === "sent").length;
  }).toBe(3);
  const response = await page.request.get(`/api/outbox?campaign_id=${campaignId}`);
  const outbox = await response.json();
  expect(new Set(outbox.items.map((item: any) => item.recipient_email)).size).toBe(3);
  await page.goto(`/outbox?campaign_id=${campaignId}`);
  await page.getByRole("button", { name: "Read message" }).first().click();
  await expect(page.getByRole("dialog").getByRole("link", { name: "instructions.txt" })).toBeVisible();
  await page.getByRole("button", { name: "Forward message" }).click();
  await page.getByLabel("Forward to").fill("registration@example.com");
  await page.getByLabel("Note (optional)").fill("Please review this invitation.");
  await page.getByRole("button", { name: "Queue sandbox forward" }).click();
  await expect(page.getByRole("status")).toContainText("Forward queued");
  await page.goto("/judges");
  await page.getByLabel("Main category").selectOption("arts");
  await page.getByLabel("Response", { exact: true }).selectOption("accepted");
  await expect(page.getByRole("row").filter({ hasText: title })).toHaveCount(3);
  await expect(page.getByRole("button", { name: "Export sheet" })).toBeVisible();
});

test("permanent competition cannot be deleted and pilot deletion has three steps", async ({ page }) => {
  const password = process.env.SEED_PASSWORD;
  if (!password) throw new Error("SEED_PASSWORD is required");
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill("director@example.com");
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("link", { name: "Competitions", exact: true }).click();
  await page.locator(".pilot-card").filter({ hasText: "Arts" }).click();
  await page.locator(".pilot-card").filter({ hasText: "2D Art" }).click();
  await expect(page.getByRole("heading", { name: "2D Art" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete pilot" })).toHaveCount(0);
  await page.goBack();
  await page.locator(".pilot-card").filter({ hasText: "Culinary Arts" }).click();
  await page.getByRole("button", { name: "Delete pilot" }).click();
  await expect(page.getByText("Are you sure you want to delete", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Yes, continue" }).click();
  await expect(page.getByText("Are you really sure?", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Continue to final confirmation" }).click();
  await page.getByLabel("Competition name").fill("Culinary Arts");
  await page.getByRole("dialog").getByRole("button", { name: "Delete pilot" }).click();
  await expect(page.getByRole("heading", { name: "Arts" })).toBeVisible();
  await expect(page.locator(".pilot-card").filter({ hasText: "Culinary Arts" })).toHaveCount(0);
  await page.locator("a.back").click();
  await page.getByRole("link", { name: "Deleted pilots" }).click();
  await expect(page.getByRole("row").filter({ hasText: "Culinary Arts" })).toContainText("Demo Director");
});
