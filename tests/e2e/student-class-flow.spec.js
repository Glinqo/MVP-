// tests/e2e/student-class-flow.spec.js
import { test, expect } from "@playwright/test";
import { collectErrors } from "./helpers/auth.js";

async function loginAsStudent(page, username) {
  await page.goto("/");
  await page.fill("#loginUsername", username);
  await page.fill("#loginPassword", "123456");
  await page.getByRole("button", { name: "登录" }).click();
}

test("student single class auto-enters class context", async ({ page }) => {
  const errors = collectErrors(page);
  await loginAsStudent(page, "001");

  // Student 001 is only in E2E-A, should auto-enter
  // Wait for student layout or class selector
  await expect(page.locator(".student-layout")).toBeVisible({ timeout: 15000 });

  // Should not show multi-class selector
  await expect(page.locator("#studentClassSelectorOverlay")).toHaveCount(0);

  expect(errors.pageErrors).toHaveLength(0);
});

test("student multi-class shows selector", async ({ page }) => {
  const errors = collectErrors(page);
  // Clear student class localStorage to force selector
  await page.goto("/");
  await page.evaluate(() => {
    localStorage.removeItem("mcp_student_class_id_011");
    localStorage.removeItem("mcp_auth_token");
    localStorage.removeItem("mcp_login_user");
  });
  await loginAsStudent(page, "011");

  // Student 011 is in both E2E-A and E2E-B
  await expect(page.locator("#studentClassSelectorOverlay")).toBeVisible({ timeout: 15000 });

  // Should show class cards
  await expect(page.locator(".student-class-card", { hasText: "E2E-A" }).first()).toBeVisible();
  await expect(page.locator(".student-class-card", { hasText: "E2E-B" }).first()).toBeVisible();

  // Select E2E-A
  await page.locator(".student-class-card", { hasText: "E2E-A" }).first().click();
  await page.waitForLoadState("networkidle");

  expect(errors.pageErrors).toHaveLength(0);
});
