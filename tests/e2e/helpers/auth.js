// tests/e2e/helpers/auth.js
import { expect } from "@playwright/test";

/**
 * Login as a teacher via UI.
 * @param {import("@playwright/test").Page} page
 * @param {string} username
 * @param {string} password
 */
export async function loginAsTeacher(page, username = "000", password = "123456") {
  await page.goto("/");
  await page.fill("#loginUsername", username);
  await page.fill("#loginPassword", password);
  await page.getByRole("button", { name: "登录" }).click();
  // Wait for teacher layout to appear
  await expect(page.locator(".teacher-layout")).toBeVisible({ timeout: 15000 });
}

/**
 * Collect browser errors during a test.
 * @param {import("@playwright/test").Page} page
 */
export function collectErrors(page) {
  const consoleErrors = [];
  const pageErrors = [];
  const serverErrors = [];

  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => pageErrors.push(err.message));
  page.on("response", (resp) => {
    if (resp.status() >= 500) serverErrors.push(`${resp.status()} ${resp.url()}`);
  });

  return { consoleErrors, pageErrors, serverErrors };
}
