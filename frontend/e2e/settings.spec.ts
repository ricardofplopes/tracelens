import { test, expect } from "@playwright/test";

test.describe("Settings Page", () => {
  test("should display system health section", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.locator("text=System Health")).toBeVisible();
  });

  test("should display providers section", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.locator("text=Provider")).toBeVisible();
  });

  test("should show theme toggle", async ({ page }) => {
    await page.goto("/settings");
    // Theme toggle should be in navbar
    const themeBtn = page.locator('button[title*="Switch to"]');
    await expect(themeBtn).toBeVisible();
  });
});
