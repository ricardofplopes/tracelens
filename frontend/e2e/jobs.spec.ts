import { test, expect } from "@playwright/test";

test.describe("Job History Page", () => {
  test("should display job history page", async ({ page }) => {
    await page.goto("/jobs");
    await expect(page.locator("text=History")).toBeVisible();
  });

  test("should show empty state or job list", async ({ page }) => {
    await page.goto("/jobs");
    // Either shows "No investigations" empty state or job rows
    const content = await page.textContent("body");
    const hasJobs = content?.includes("complete") || content?.includes("processing");
    const hasEmpty = content?.includes("No investigation") || content?.includes("No jobs") || content?.includes("empty");
    expect(hasJobs || hasEmpty).toBe(true);
  });
});
