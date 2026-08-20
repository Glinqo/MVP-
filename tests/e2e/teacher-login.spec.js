// tests/e2e/teacher-login.spec.js
import { test, expect } from "@playwright/test";
import { loginAsTeacher, collectErrors } from "./helpers/auth.js";

test("teacher 000 login shows teacher workspace", async ({ page }) => {
  const errors = collectErrors(page);
  await loginAsTeacher(page, "000", "123456");

  // Teacher uses the same full chat skeleton as students
  await expect(page.locator(".student-layout")).toBeVisible();
  await expect(page.locator(".teacher-layout")).toHaveCount(0);

  // Key teacher UI elements
  await expect(page.locator("#teacherClassLabel")).toBeVisible();
  await expect(page.locator("#createClassBtn")).toBeVisible();
  await expect(page.locator("#chatForm")).toBeVisible();
  await expect(page.locator(".launcher-panel.role-teacher")).toBeVisible();

  // No legacy landingStepStudents
  await expect(page.locator("#landingStepStudents")).toHaveCount(0);

  // No page errors or 5xx
  expect(errors.pageErrors).toHaveLength(0);
  expect(errors.serverErrors).toHaveLength(0);
});
