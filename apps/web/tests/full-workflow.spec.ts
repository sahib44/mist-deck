import { test, expect } from "@playwright/test";
import path from "node:path";

test("organizer imports, reviews, campaigns, and resolves a support ticket", async ({
  page, playwright, baseURL,
}) => {
  page.on("dialog", (dialog) => dialog.accept());
  const stamp = Date.now();
  const dateFromNow = (days: number) =>
    new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);
  const login = async (email: string) => {
    const password = process.env.SEED_PASSWORD;
    if (!password) throw new Error("SEED_PASSWORD is required");
    await page.goto("/login");
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Operations overview" }),
    ).toBeVisible();
  };
  await login("competitions@example.com");
  await expect(page.getByRole("navigation", { name: "Judge handling" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Competitions tickets" })).toBeVisible();
  await page.getByRole("button", { name: "Switch to dark mode" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Switch to light mode" }).click();
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(page.locator(".app")).toHaveClass(/sidebar-collapsed/);
  await page.getByRole("button", { name: "Expand sidebar" }).click();
  await expect(page.locator(".app")).not.toHaveClass(/sidebar-collapsed/);
  await expect(
    page.getByText("SANDBOX EMAIL MODE", { exact: true }),
  ).toBeVisible();
  await page.goto("/imports/new");
  await page
    .getByLabel("CSV file")
    .setInputFiles(
      process.env.SAMPLE_DATA
        ? path.join(process.env.SAMPLE_DATA, "mock_judges_with_duplicates.csv")
        : path.resolve("../../sample-data/mock_judges_with_duplicates.csv"),
    );
  await page.getByRole("button", { name: "Upload and continue" }).click();
  await expect(
    page.getByRole("heading", { name: "Match CSV columns to contact fields" }),
  ).toBeVisible();
  await expect(page.getByLabel("Primary Email", { exact: true })).toHaveValue(
    "primary_email",
  );
  await page.getByRole("button", { name: "Analyze rows" }).click();
  await expect(
    page.getByRole("heading", { name: "Row analysis" }),
  ).toBeVisible();
  const batchId = page.url().split("/imports/")[1];
  let exact = false,
    possible = false;
  await page
    .getByRole("link", { name: "Review duplicates", exact: true })
    .click();
  for (let i = 0; i < 20; i++) {
    const response = await page.request.get(
      `/api/duplicates?batch_id=${batchId}&page_size=100`,
    );
    const strong = (await response.json()).items.filter(
      (r: any) => r.confidence_score >= 0.7,
    );
    if (!strong.length) break;
    const candidate = strong[0];
    exact ||= candidate.match_type === "exact_email";
    possible ||= ["name_organization", "similar_organization"].includes(
      candidate.match_type,
    );
    await page.goto("/duplicates/" + candidate.id);
    await expect(
      page.getByRole("heading", { name: "Compare & resolve" }),
    ).toBeVisible();
    await page.getByLabel("Keep Organization").selectOption("incoming");
    await page
      .getByLabel("I reviewed the matching evidence and field selections.")
      .check();
    await page.getByRole("button", { name: "Confirm resolution" }).click();
    await expect(page).toHaveURL(/\/duplicates\?batch_id=/);
  }
  expect(exact).toBe(true);
  expect(possible).toBe(true);
  await page.goto("/imports/" + batchId);
  await page.getByRole("button", { name: "Continue to commit" }).click();
  await page
    .getByLabel("I reviewed the analysis and approve these changes.")
    .check();
  await page
    .getByRole("button", { name: "Commit import", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Import complete" }),
  ).toBeVisible();
  await page.goto("/judges");
  await page.getByLabel("Select visible judges").check();
  await page.getByRole("button", { name: "Email selected", exact: true }).click();
  await expect(page.getByLabel("Selected recipients")).not.toBeEmpty();
  await page
    .getByLabel("Campaign name", { exact: true })
    .fill("Arts invitation " + stamp);
  await page.getByLabel("Event date", { exact: true }).fill(dateFromNow(30));
  await page
    .getByLabel("Response deadline", { exact: true })
    .fill(dateFromNow(14));
  await page.getByRole("button", { name: "Create draft & preview" }).click();
  await expect(page.getByRole("heading", { name: "Review recipient exclusions", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "Continue to preview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Arts invitation " + stamp }),
  ).toBeVisible();
  const campaignId = page.url().split("/campaigns/")[1];
  const preview = await page.request.get(
    `/api/campaigns/${campaignId}/preview?page_size=100`,
  );
  const recipients = (await preview.json()).items;
  expect(recipients.length).toBeGreaterThan(0);
  for (const recipient of recipients) {
    await page
      .getByRole("button", {
        name: new RegExp(
          recipient.recipient_email.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
        ),
      })
      .click();
    await expect(
      page.locator(".email-preview .message-body"),
    ).not.toContainText("{{");
  }
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await page
    .getByRole("button", { name: "Approve campaign", exact: true })
    .click();
  await page.getByRole("button", { name: "Queue sandbox delivery" }).click();
  await expect
    .poll(async () => {
      const r = await page.request.get(`/api/campaigns/${campaignId}`);
      return (await r.json()).status;
    })
    .toBe("completed");
  await page.getByRole("link", { name: "View sandbox outbox" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(recipients.length);
  const outbox = await page.request.get(
    "/api/outbox?campaign_id=" + campaignId,
  );
  const messages = (await outbox.json()).items;
  expect(new Set(messages.map((m: any) => m.recipient_email)).size).toBe(
    recipients.length,
  );
  expect(
    messages.every((m: any) => m.status === "sent" && m.attempt_count === 1),
  ).toBe(true);
  await page.goto("/tickets/new");
  await page.getByLabel("Requester name").fill("Fictional Competitor E2E");
  await page.getByLabel("Requester email").fill("competitor-e2e@example.org");
  await page
    .getByLabel("Subject", { exact: true })
    .fill("Arts submission question " + stamp);
  await page
    .getByLabel("Message body", { exact: true })
    .fill("May I update my fabricated arts entry?");
  for (const field of ["Category", "Committee", "Priority"]) {
    await expect(page.getByLabel(field, { exact: true })).toHaveCount(0);
  }
  await page.getByRole("button", { name: "Create simulated ticket" }).click();
  await expect(
    page.getByRole("heading", { name: "Arts submission question " + stamp }),
  ).toBeVisible();
  const ticketId = page.url().split("/tickets/")[1];
  for (const field of ["Assigned organizer", "Competition category", "Committee", "Ticket priority"]) {
    await expect(page.getByLabel(field, { exact: true })).toHaveCount(0);
  }
  await expect(page.getByRole("button", { name: "Save assignment" })).toHaveCount(0);
  await page
    .getByRole("button", { name: "Internal note", exact: true })
    .click();
  await page
    .getByLabel("Private internal note", { exact: true })
    .fill("Private: organizer review completed.");
  await page
    .getByRole("button", { name: "Save private internal note" })
    .click();
  await expect(page.locator(".private-notes")).toContainText(
    "Private: organizer review completed.",
  );
  for (const theme of ["light", "dark"]) {
    if (theme === "dark") await page.getByRole("button", { name: "Switch to dark mode" }).click();
    const surface = await page.locator(".ticket-layout .panel").first().evaluate(element => getComputedStyle(element).backgroundColor);
    for (const selector of [".composer.private", ".composer.private textarea", ".private-notes-panel", ".private-notes"]) {
      await expect.poll(() => page.locator(selector).evaluate(element => getComputedStyle(element).backgroundColor)).toBe(surface);
      await expect.poll(() => page.locator(selector).evaluate(element => getComputedStyle(element).borderTopColor)).toBe(theme === "dark" ? "rgb(227, 189, 69)" : "rgb(180, 138, 18)");
    }
    await page.screenshot({ path: `test-results/internal-notes-${theme}.png`, fullPage: true });
  }
  await page.getByRole("button", { name: "Switch to light mode" }).click();

  expect(
    (await (await page.request.get("/api/outbox?ticket_id=" + ticketId)).json())
      .total,
  ).toBe(0);
  await page.getByRole("button", { name: "Public reply", exact: true }).click();
  await page
    .getByLabel("Public reply body")
    .fill("Yes, your fabricated entry may be updated.");
  await expect(page.getByRole("button", { name: "Send public sandbox reply" })).toBeDisabled();
  await page.getByRole("button", { name: "Request chair approval", exact: true }).click();
  await expect(page.getByRole("button", { name: "Awaiting chair approval", exact: true })).toBeVisible();
  const draft = (await (await page.request.get(`/api/tickets/${ticketId}/drafts`)).json()).items[0];
  const chairApi = await playwright.request.newContext({ baseURL });
  await chairApi.post("/api/auth/login", { data: { email: "chair@example.com", password: process.env.SEED_PASSWORD } });
  const approval = await chairApi.post(`/api/tickets/${ticketId}/drafts/${draft.id}/approve`, { headers: { "X-MIST-Request": "1" } });
  expect(approval.ok()).toBe(true);
  await chairApi.dispose();
  await expect(page.getByRole("button", { name: "Send public sandbox reply" })).toBeEnabled();
  await page.getByRole("button", { name: "Send public sandbox reply" }).click();
  await expect(page.locator(".conversation.staff_reply")).toContainText(
    "Yes, your fabricated entry may be updated.",
  );
  await expect
    .poll(async () => {
      const result = await (
        await page.request.get("/api/outbox?ticket_id=" + ticketId)
      ).json();
      return result.items[0]?.status;
    })
    .toBe("sent");
  await page
    .getByLabel("Ticket status", { exact: true })
    .selectOption("resolved");
  await expect(page.getByRole("button", { name: "Update status", exact: true }).last()).toBeDisabled();
  await page.getByLabel("Resolution note", { exact: true }).fill("Confirmed the submission can be updated.");
  await page.locator("aside").getByRole("button", { name: "Update status", exact: true }).click();
  await expect(
    page.locator(".page-heading .badge").filter({ hasText: "Resolved" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Forward email", exact: true }).first().click();
  await page.getByLabel("Forward to", { exact: true }).fill("registration@example.org");
  await page.getByLabel("Note (optional)").fill("Please review this question.");
  await page.getByRole("button", { name: "Queue sandbox forward", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Forward queued" })).toBeVisible();
  const forwarded = (await (await page.request.get(`/api/outbox?ticket_id=${ticketId}&q=registration`)).json()).items[0];
  expect(forwarded.body_text).toContain("May I update my fabricated arts entry?");
  expect(forwarded.body_text).not.toContain("Private: organizer review completed.");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByLabel("Email", { exact: true })).toBeVisible();
  await login("director@example.com");
  await page.goto("/audit");
  await page.getByLabel("Search audit events").fill("ticket.status_changed");
  await expect(page.locator("tbody")).toContainText("Ticket status: resolved");
  await page.goto("/dashboard");
  await expect(page.getByText("Judge contacts")).toBeVisible();
  await page.screenshot({ path: "test-results/dashboard.png", fullPage: true });
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(page.getByRole('link', { name: 'Judge directory', exact: true })).not.toBeVisible();
  await page.getByRole('button', { name: 'Toggle navigation' }).click();
  await expect(page.getByRole('link', { name: 'Judge directory', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Close navigation' }).click();
  await expect(page.getByRole('link', { name: 'Judge directory', exact: true })).not.toBeVisible();
  await page.screenshot({ path: "test-results/tablet.png", fullPage: true });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
