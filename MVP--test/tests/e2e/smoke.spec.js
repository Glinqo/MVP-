// tests/e2e/smoke.spec.js
import { test, expect } from "@playwright/test";
import { collectErrors } from "./helpers/auth.js";

test("health check and page loads without errors", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/");
  await expect(page).toHaveTitle(/机电岗位培训 AI/);
  await expect(page.locator("#landingOverlay")).toBeVisible();
  await expect(page.locator("#loginUsername")).toBeVisible();
  expect(errors.pageErrors).toHaveLength(0);
  expect(errors.serverErrors).toHaveLength(0);
});
