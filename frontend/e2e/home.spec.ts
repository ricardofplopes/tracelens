import { test, expect } from "@playwright/test";

test.describe("Home Page", () => {
  test("should display the upload form", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("text=TraceLens")).toBeVisible();
    // Check for upload area
    await expect(page.locator("text=upload")).toBeVisible();
  });

  test("should show URL input option", async ({ page }) => {
    await page.goto("/");
    // Look for URL tab/option
    await expect(page.locator("text=URL")).toBeVisible();
  });

  test("should validate empty submission", async ({ page }) => {
    await page.goto("/");
    // Try to submit without an image — button should be disabled or show error
    const submitBtn = page.locator('button[type="submit"], button:has-text("Investigate"), button:has-text("Analyze")');
    if (await submitBtn.count() > 0) {
      // If there's a submit button, it should be disabled without input
      const isDisabled = await submitBtn.first().isDisabled();
      expect(isDisabled).toBe(true);
    }
  });
});
