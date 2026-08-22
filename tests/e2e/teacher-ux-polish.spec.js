import { test, expect, request } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { collectErrors, loginAsTeacher } from "./helpers/auth.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const BASE_URL = "http://127.0.0.1:8765";
const JOB_ROLE = "automation_line_commissioning_maintenance_newcomer";

let teacherToken = "";
let classA = null;
let classB = null;
let classAName = "";
let classBName = "";
let createdPrefix = "";

async function loginTeacher(ctx) {
  const resp = await ctx.post("/api/auth/login", {
    data: { username: "000", password: "123456" },
  });
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  return body.token;
}

async function createClass(ctx, token, name, jobRole = JOB_ROLE) {
  const resp = await ctx.post("/api/teacher/classes", {
    headers: { Authorization: `Bearer ${token}` },
    data: { name, job_role: jobRole, term: "2026-ux-v3" },
  });
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  return body.class;
}

async function addStudents(ctx, token, classId, usernames) {
  const resp = await ctx.post(`/api/teacher/classes/${classId}/students`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { student_usernames: usernames },
  });
  expect(resp.ok()).toBeTruthy();
}

async function archiveClass(ctx, token, classId) {
  await ctx.post(`/api/teacher/classes/${classId}/archive`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

function seedTeacherEvidence(jobRole, students) {
  const script = `
import json
import os
import time
from app.services.assessment_store import save_state
from app.services.feedback import append_session_event

job_role = os.environ["E2E_JOB_ROLE"]
students = json.loads(os.environ["E2E_STUDENTS"])
now = time.time()

for username in students:
    session_id = f"{job_role}-{username}"
    for i in range(4):
        append_session_event(session_id, {
            "event_type": "initial_quiz_answered",
            "ability_id": "sn_type_identify",
            "is_correct": False,
            "source": "playwright_teacher_ux_v3",
        })
    append_session_event(session_id, {
        "event_type": "question_explained",
        "ability_id": "pl_program_monitor",
        "source": "playwright_teacher_ux_v3",
    })
    save_state({
        "session_id": session_id,
        "job_role": job_role,
        "assessment_id": "PW-" + session_id,
        "assessment_version": "1.0.0",
        "state": "completed",
        "answers": [],
        "result": {
            "total_score": 35,
            "weak_abilities": ["sn_type_identify"],
            "strong_abilities": ["pl_program_monitor"],
        },
        "completed_at": now,
    })
`;
  execFileSync("python", ["-c", script], {
    cwd: ROOT,
    env: {
      ...process.env,
      E2E_JOB_ROLE: jobRole,
      E2E_STUDENTS: JSON.stringify(students),
    },
    stdio: "pipe",
  });
}

async function openStudentManagement(page) {
  const overlayOpen = await page.locator("#workspaceOverlay").evaluate((el) =>
    el.classList.contains("open")
  );
  if (overlayOpen) {
    await page.locator("#closeWorkspace").click();
  }
  await page.locator('[data-open-tool="studentMgmt"]').click();
  await expect(page.locator("#workspaceOverlay")).toHaveClass(/open/);
  await page.locator('[data-workspace-panel="studentMgmt"]').click();
  await expect(page.locator("#teacherClassLabel")).toBeVisible();
}

async function selectClass(page, name) {
  await openStudentManagement(page);
  await page.locator("#teacherClassLabel").click();
  await expect(page.locator("#classDropdown")).toBeVisible();
  await page.locator(".class-dropdown-item", { hasText: name }).first().click();
  await expect(page.locator("#teacherClassLabel")).toContainText(name);
}

async function openTodayAndIssue(page) {
  await page.locator('[data-workspace-panel="teacherToday"]').click();
  await expect(page.locator("#todayTeachingContent .issue-card").first()).toBeVisible({ timeout: 15000 });
  await page.locator("#todayTeachingContent .issue-card").first().click();
  await expect(page.locator("#issueDetailDrawer")).toHaveClass(/open/);
}

test.describe.serial("Teacher UX Polish V3", () => {
  test.beforeAll(async () => {
    const stamp = Date.now();
    createdPrefix = `E2E-UX-${stamp}`;
    classAName = `${createdPrefix}-A`;
    classBName = `${createdPrefix}-B`;

    const ctx = await request.newContext({ baseURL: BASE_URL });
    teacherToken = await loginTeacher(ctx);
    classA = await createClass(ctx, teacherToken, classAName, JOB_ROLE);
    classB = await createClass(ctx, teacherToken, classBName, "mechanical_electrical_maintenance_worker");
    await addStudents(ctx, teacherToken, classA.id, ["001", "002"]);
    await addStudents(ctx, teacherToken, classB.id, ["006", "007"]);
    seedTeacherEvidence(JOB_ROLE, ["001", "002"]);
    await ctx.post("/api/teacher/comments/generate", {
      headers: { Authorization: `Bearer ${teacherToken}` },
      data: { student_id: "001", class_id: classA.id, job_role: JOB_ROLE },
    });
    await ctx.dispose();
  });

  test.afterAll(async () => {
    if (!teacherToken || !createdPrefix) return;
    const ctx = await request.newContext({ baseURL: BASE_URL });
    const resp = await ctx.get("/api/teacher/classes", {
      headers: { Authorization: `Bearer ${teacherToken}` },
    });
    const body = await resp.json();
    for (const cls of body.classes || []) {
      if (String(cls.name || "").startsWith(createdPrefix)) {
        await archiveClass(ctx, teacherToken, cls.id);
      }
    }
    await ctx.dispose();
  });

  test("UX-01 全局班级上下文", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    for (const panel of ["teacherToday", "classInsights", "studentMgmt", "teacherComments"]) {
      await page.locator(`[data-workspace-panel="${panel}"]`).click();
      await expect(page.locator("#teacherClassLabel")).toContainText(classAName);
      await expect(page.locator("#teacherClassMeta")).toBeVisible();
    }
  });

  test("UX-02 导航顺序", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    const labels = await page.locator(".workspace-tabs .role-teacher").allTextContents();
    expect(labels.map((text) => text.trim())).toEqual([
      "今日教学",
      "班级洞察",
      "学生",
      "教学反馈",
      "岗位图谱"
    ]);
  });

  test("UX-03 无明显英文系统词", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="teacherToday"]').click();
    await expect(page.locator("#todayTeachingContent .issue-card").first()).toBeVisible({ timeout: 15000 });
    const forbidden = ["high", "mid", "low", "Loading", "Student", "events", "draft", "reviewed", "published", "Added", "Removed", "Parse result"];
    const bodyText = await page.locator("body").innerText();
    for (const word of forbidden) {
      expect(bodyText, `不应出现 ${word}`).not.toContain(word);
    }
  });

  test("UX-04 Ability 中文显示", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await openTodayAndIssue(page);
    await expect(page.locator("#issueDetailDrawer")).not.toContainText("sn_type_identify");
    await expect(page.locator("#issueDetailDrawer")).toContainText("PLC 程序监控");
    await page.locator(".issue-drawer-close").click();
    await page.locator('[data-workspace-panel="studentMgmt"]').click();
    await expect(page.locator('#teacherStudentListPane .student-card[data-student-id="001"]').first()).toBeVisible({ timeout: 15000 });
    await page.locator('#teacherStudentListPane .student-card[data-student-id="001"]').click();
    await expect(page.locator("#teacherStudentDetailPane")).not.toContainText("sn_type_identify");
    await expect(page.locator("#teacherStudentDetailPane")).toContainText("传感器类型识别");
  });

  test("UX-05 Issue 一眼可读", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="teacherToday"]').click();
    await expect(page.locator("#todayTeachingContent .issue-card").first()).toBeVisible({ timeout: 15000 });
    const card = page.locator("#todayTeachingContent .issue-card").first();
    await expect(card).toContainText("优先处理");
    await expect(card).toContainText("名学生受到影响");
    await expect(card).toContainText("主要能力");
    await expect(card).not.toContainText("confidence");
    await expect(card).not.toContainText("severity");
  });

  test("UX-06 AI 调整无硬编码学生", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await openTodayAndIssue(page);
    await page.getByRole("button", { name: "生成干预方案" }).click();
    await expect(page.locator("#issueDetailDrawer .candidate-card").first()).toBeVisible({ timeout: 15000 });
    await page.locator("#issueDetailDrawer .candidate-adopt").first().click();
    await page.locator("#issueDetailDrawer").getByRole("button", { name: "让 AI 调整" }).click();
    await expect(page.locator("#chatInput")).not.toHaveValue(/001/);
  });

  test("UX-07 无浏览器 alert", async ({ page }) => {
    const dialogs = [];
    page.on("dialog", async (dialog) => {
      dialogs.push(dialog.message());
      await dialog.accept();
    });
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await openStudentManagement(page);
    await page.locator("#manageClassBtn").click();
    await expect(page.locator("#manageStudentsModal")).toBeVisible();
    await page.locator("#studentSearchInput").fill("003");
    await expect(page.locator('#studentManageList .student-manage-check[data-username="003"]').first()).toBeVisible();
    await page.locator('#studentManageList .student-manage-check[data-username="003"]').check();
    await page.getByRole("button", { name: "加入班级" }).click();
    await expect(page.locator(".teacher-toast-success").last()).toContainText("已加入");
    expect(dialogs).toHaveLength(0);
    await page.locator("#studentSearchInput").fill("003");
    await page.locator('#studentManageList .student-manage-check[data-username="003"]').check();
    await page.getByRole("button", { name: "移除选中" }).click();
    await expect(page.locator(".teacher-toast-success").last()).toContainText("已移除");
    expect(dialogs).toHaveLength(0);
  });

  test("UX-08 学生选中态", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="studentMgmt"]').click();
    await expect(page.locator('#teacherStudentListPane .student-card[data-student-id="001"]').first()).toBeVisible({ timeout: 15000 });
    await page.locator('#teacherStudentListPane .student-card[data-student-id="001"]').click();
    await expect(page.locator('#teacherStudentListPane .student-card[data-student-id="001"]')).toHaveClass(/active/);
    await page.locator('#teacherStudentListPane .student-card[data-student-id="002"]').click();
    await expect(page.locator('#teacherStudentListPane .student-card[data-student-id="001"]')).not.toHaveClass(/active/);
    await expect(page.locator('#teacherStudentListPane .student-card[data-student-id="002"]')).toHaveClass(/active/);
  });

  test("UX-09 教学反馈状态", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="teacherComments"]').click();
    await expect(page.locator("#tw-feedback .comment-card").first()).toBeVisible({ timeout: 15000 });
    await expect(page.locator("#tw-feedback")).toContainText("草稿");
    const feedbackText = await page.locator("#tw-feedback").innerText();
    for (const word of ["draft", "reviewed", "published"]) {
      expect(feedbackText).not.toContain(word);
    }
  });

  test("UX-10 班级切换", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="studentMgmt"]').click();
    await expect(page.locator('#teacherStudentListPane .student-card[data-student-id="001"]').first()).toBeVisible({ timeout: 15000 });
    await selectClass(page, classBName);
    await expect(page.locator("#teacherClassLabel")).toContainText(classBName);
    await page.locator('[data-workspace-panel="studentMgmt"]').click();
    await expect(page.locator('#teacherStudentListPane .student-card[data-student-id="006"]').first()).toBeVisible({ timeout: 15000 });
    await expect(page.locator('#teacherStudentListPane .student-card[data-student-id="001"]')).toHaveCount(0);
  });
});
