// tests/e2e/teacher-login.spec.js
import { test, expect } from "@playwright/test";
import { loginAsTeacher, collectErrors } from "./helpers/auth.js";

test("teacher 000 login shows teacher workspace", async ({ page }) => {
  const errors = collectErrors(page);
  await loginAsTeacher(page, "000", "123456");

  // Teacher layout visible, student layout hidden
  await expect(page.locator(".teacher-layout")).toBeVisible();
  await expect(page.locator(".student-layout")).toBeHidden();

  // Key teacher UI elements
  await expect(page.locator("#teacherClassLabel")).toBeVisible();
  await expect(page.locator("#createClassBtn")).toBeVisible();
  await expect(page.locator("#teacherChatForm")).toBeVisible();

  // No legacy landingStepStudents
  await expect(page.locator("#landingStepStudents")).toHaveCount(0);

  // No page errors or 5xx
  expect(errors.pageErrors).toHaveLength(0);
  expect(errors.serverErrors).toHaveLength(0);
});
