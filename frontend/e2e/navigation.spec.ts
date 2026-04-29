import { test, expect } from "@playwright/test";

test.describe("Navigation", () => {
  test("should navigate to history page", async ({ page }) => {
    await page.goto("/");
    await page.click('a[href="/jobs"]');
    await expect(page).toHaveURL("/jobs");
  });

  test("should navigate to settings page", async ({ page }) => {
    await page.goto("/");
    await page.click('a[href="/settings"]');
    await expect(page).toHaveURL("/settings");
  });

  test("should have working navbar links", async ({ page }) => {
    await page.goto("/settings");
    await page.click('a[href="/"]');
    await expect(page).toHaveURL("/");
  });
});
