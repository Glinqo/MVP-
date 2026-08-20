// tests/e2e/teacher-class-flow.spec.js
import { test, expect } from "@playwright/test";
import { loginAsTeacher, collectErrors } from "./helpers/auth.js";
import { getTeacherToken, apiCreateClass, apiAddStudents, apiListClasses } from "./helpers/setup.js";

let classAId = null;
let classBId = null;

test.beforeAll(async () => {
  const token = await getTeacherToken();
  // Archive old test classes
  const existing = await apiListClasses(token);
  for (const c of existing) {
    if (c.name === "E2E-A" || c.name === "E2E-B") {
      const ctx = await import("@playwright/test").then(m => m.request);
      const rc = await ctx.newContext({ baseURL: "http://127.0.0.1:8765" });
      await rc.post(`/api/teacher/classes/${c.id}/archive`, { headers: { Authorization: `Bearer ${token}` } });
      await rc.dispose();
    }
  }
  // Create fresh classes
  classAId = await apiCreateClass(token, "E2E-A", "automation_line_commissioning_maintenance_newcomer");
  classBId = await apiCreateClass(token, "E2E-B", "mechanical_electrical_maintenance_worker");
  await apiAddStudents(token, classAId, ["001", "002", "003", "011"]);
  await apiAddStudents(token, classBId, ["006", "007", "008", "011"]);
});

test("teacher login and students roster class-scoped", async ({ page }) => {
  const errors = collectErrors(page);
  await loginAsTeacher(page, "000", "123456");

  // Click class label to open dropdown
  await page.locator("#teacherClassLabel").click();
  // Wait for dropdown to appear
  await expect(page.locator("#classDropdown")).toBeVisible();

  // Select E2E-A class
  await page.locator(".class-dropdown-item", { hasText: "E2E-A" }).first().click();

  // Open Students module from the shared teacher launcher
  await page.locator('[data-open-tool="studentMgmt"]').click();
  await expect(page.locator("#workspaceOverlay")).toHaveClass(/open/);

  // Wait for roster to load
  await expect(page.locator("#teacherStudentListPane")).toBeVisible();
  // Check E2E-A students present
  await expect(page.locator(".student-card", { hasText: "001" }).first()).toBeVisible({ timeout: 15000 });

  // E2E-B students must NOT be visible
  await expect(page.locator(".student-card", { hasText: "006" })).toHaveCount(0);

  expect(errors.pageErrors).toHaveLength(0);
  expect(errors.serverErrors).toHaveLength(0);
});

test("teacher A to B to A switch no cross-class", async ({ page }) => {
  const errors = collectErrors(page);
  await loginAsTeacher(page, "000", "123456");

  // Select E2E-A
  await page.locator("#teacherClassLabel").click();
  await expect(page.locator("#classDropdown")).toBeVisible();
  await page.locator(".class-dropdown-item", { hasText: "E2E-A" }).first().click();
  await page.locator('[data-open-tool="studentMgmt"]').click();
  await expect(page.locator(".student-card", { hasText: "001" }).first()).toBeVisible({ timeout: 15000 });

  // Switch to E2E-B
  await page.locator("#closeWorkspace").click();
  await page.locator("#teacherClassLabel").click();
  await expect(page.locator("#classDropdown")).toBeVisible();
  await page.locator(".class-dropdown-item", { hasText: "E2E-B" }).first().click();
  await page.locator('[data-open-tool="studentMgmt"]').click();
  // Students should reload to B roster
  await expect(page.locator(".student-card", { hasText: "006" }).first()).toBeVisible({ timeout: 15000 });
  // A students must be gone
  await expect(page.locator(".student-card", { hasText: "001" })).toHaveCount(0);

  // Switch back to E2E-A
  await page.locator("#closeWorkspace").click();
  await page.locator("#teacherClassLabel").click();
  await expect(page.locator("#classDropdown")).toBeVisible();
  await page.locator(".class-dropdown-item", { hasText: "E2E-A" }).first().click();
  await page.locator('[data-open-tool="studentMgmt"]').click();
  await expect(page.locator(".student-card", { hasText: "001" }).first()).toBeVisible({ timeout: 15000 });

  expect(errors.pageErrors).toHaveLength(0);
});

test("teacher AI rejects out-of-class student", async ({ page }) => {
  const errors = collectErrors(page);
  await loginAsTeacher(page, "000", "123456");

  // Select E2E-A
  await page.locator("#teacherClassLabel").click();
  await expect(page.locator("#classDropdown")).toBeVisible();
  await page.locator(".class-dropdown-item", { hasText: "E2E-A" }).first().click();

  // Ask AI about student 008 (in E2E-B, not E2E-A)
  await page.fill("#chatInput", "查看学生 008 的学习状态");
  await page.getByRole("button", { name: "发送" }).click();

  // Wait for AI response
  await expect(page.locator("#chatMessages")).toContainText("不属于当前班级", { timeout: 15000 });

  expect(errors.pageErrors).toHaveLength(0);
});
