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
    data: { name, job_role: jobRole, term: "2026-ai-v2" },
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
            "source": "playwright_teacher_ai_v2",
        })
    append_session_event(session_id, {
        "event_type": "question_explained",
        "ability_id": "pl_program_monitor",
        "source": "playwright_teacher_ai_v2",
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
  await expect(page.locator("#teacherClassLabel")).not.toHaveText("未选择班级", { timeout: 15000 });
}

async function selectClass(page, name) {
  await openStudentManagement(page);
  await page.locator("#teacherClassLabel").click();
  await expect(page.locator("#classDropdown")).toBeVisible();
  await page.locator(".class-dropdown-item", { hasText: name }).first().click();
  await expect(page.locator("#teacherClassLabel")).toContainText(name);
}

async function ask(page, text) {
  await page.fill("#chatInput", text);
  await page.getByRole("button", { name: "发送" }).click();
}

test.describe.serial("Teacher AI Workflow V2", () => {
  test.beforeAll(async () => {
    const stamp = Date.now();
    createdPrefix = `E2E-AI-${stamp}`;
    classAName = `${createdPrefix}-A`;
    classBName = `${createdPrefix}-B`;

    const ctx = await request.newContext({ baseURL: BASE_URL });
    teacherToken = await loginTeacher(ctx);
    classA = await createClass(ctx, teacherToken, classAName, JOB_ROLE);
    classB = await createClass(ctx, teacherToken, classBName, "mechanical_electrical_maintenance_worker");
    await addStudents(ctx, teacherToken, classA.id, ["001", "002"]);
    await addStudents(ctx, teacherToken, classB.id, ["006", "007"]);
    seedTeacherEvidence(JOB_ROLE, ["001", "002"]);
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

  test("AI-01 当前 Issue 为什么", async ({ page }) => {
    const errors = collectErrors(page);
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="teacherToday"]').click();
    await expect(page.locator("#todayTeachingContent .issue-card").first()).toBeVisible({ timeout: 15000 });
    await page.locator("#todayTeachingContent .issue-card").first().click();
    await expect(page.locator("#issueDetailDrawer")).toHaveClass(/open/);
    await page.locator(".issue-drawer-close").click();
    await page.locator("#closeWorkspace").click();

    await ask(page, "为什么？");
    await expect(page.locator("#chatMessages")).toContainText("学生", { timeout: 15000 });
    await expect(page.locator("#chatMessages")).not.toContainText("请指定问题");
    expect(errors.pageErrors).toHaveLength(0);
    expect(errors.serverErrors).toHaveLength(0);
  });

  test("AI-02 连续追问教学建议", async ({ page }) => {
    const errors = collectErrors(page);
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="teacherToday"]').click();
    await expect(page.locator("#todayTeachingContent .issue-card").first()).toBeVisible({ timeout: 15000 });
    await page.locator("#todayTeachingContent .issue-card").first().click();
    await page.locator(".issue-drawer-close").click();
    await page.locator("#closeWorkspace").click();

    await ask(page, "那应该怎么教？");
    await expect(page.locator("#chatMessages")).toContainText("建议用时", { timeout: 15000 });
    await expect(page.locator("#chatMessages .ai-action-btn", { hasText: "生成方案" })).toBeVisible();
    expect(errors.serverErrors).toHaveLength(0);
  });

  test("AI-03 Candidate 教师可读", async ({ page }) => {
    const errors = collectErrors(page);
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="teacherToday"]').click();
    await expect(page.locator("#todayTeachingContent .issue-card").first()).toBeVisible({ timeout: 15000 });
    await page.locator("#todayTeachingContent .issue-card").first().click();
    await page.getByRole("button", { name: "生成干预方案" }).click();
    await expect(page.locator("#issueDetailDrawer .candidate-card").first()).toBeVisible({ timeout: 15000 });
    await expect(page.locator("#issueDetailDrawer")).toContainText("建议用时");
    await expect(page.locator("#issueDetailDrawer")).toContainText("教学目标");
    await expect(page.locator("#issueDetailDrawer")).toContainText("查看方案");
    expect(errors.serverErrors).toHaveLength(0);
  });

  test("AI-04 自然语言修改方案", async ({ page }) => {
    const errors = collectErrors(page);
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="teacherToday"]').click();
    await expect(page.locator("#todayTeachingContent .issue-card").first()).toBeVisible({ timeout: 15000 });
    await page.locator("#todayTeachingContent .issue-card").first().click();
    await page.getByRole("button", { name: "生成干预方案" }).click();
    await expect(page.locator("#issueDetailDrawer .candidate-card").first()).toBeVisible({ timeout: 15000 });
    await page.locator("#issueDetailDrawer .candidate-adopt").first().click();
    await page.locator("#issueDetailDrawer").getByRole("button", { name: "让 AI 调整" }).click();
    await ask(page, "改成20分钟，并把001单独安排。");
    await expect(page.locator("#chatMessages")).toContainText("20 分钟", { timeout: 15000 });
    await expect(page.locator("#chatMessages")).toContainText("001");
    await expect(page.locator("#chatMessages .ai-action-btn", { hasText: "采用方案" })).toBeVisible();
    expect(errors.serverErrors).toHaveLength(0);
  });

  test("AI-05 UI 确认创建正式干预", async ({ page }) => {
    const errors = collectErrors(page);
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="teacherToday"]').click();
    await expect(page.locator("#todayTeachingContent .issue-card").first()).toBeVisible({ timeout: 15000 });
    await page.locator("#todayTeachingContent .issue-card").first().click();
    await page.getByRole("button", { name: "生成干预方案" }).click();
    await expect(page.locator("#issueDetailDrawer .candidate-card").first()).toBeVisible({ timeout: 15000 });
    await page.locator("#issueDetailDrawer .candidate-adopt").first().click();
    await page.getByRole("button", { name: "采用此方案" }).click();
    await expect(page.locator("#issueDetailDrawer")).toContainText("方案已保存", { timeout: 15000 });
    await expect(page.locator("#issueDetailDrawer")).toContainText("方案草稿");
    expect(errors.pageErrors).toHaveLength(0);
    expect(errors.serverErrors).toHaveLength(0);
  });

  test("AI-06 当前学生上下文", async ({ page }) => {
    const errors = collectErrors(page);
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="studentMgmt"]').click();
    await expect(page.locator('#teacherStudentListPane .student-card[data-student-id="001"]').first()).toBeVisible({ timeout: 15000 });
    await page.locator('#teacherStudentListPane .student-card[data-student-id="001"]').click();
    await page.locator("#closeWorkspace").click();
    await ask(page, "为什么他最近表现不好？");
    await expect(page.locator("#chatMessages")).toContainText("学生 001", { timeout: 15000 });
    await expect(page.locator("#chatMessages")).not.toContainText("请先选择");
    expect(errors.serverErrors).toHaveLength(0);
  });

  test("AI-07 班级切换上下文隔离", async ({ page }) => {
    const errors = collectErrors(page);
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="teacherToday"]').click();
    await expect(page.locator("#todayTeachingContent .issue-card").first()).toBeVisible({ timeout: 15000 });
    await page.locator("#todayTeachingContent .issue-card").first().click();
    await page.locator(".issue-drawer-close").click();
    await selectClass(page, classBName);
    await page.locator("#closeWorkspace").click();
    await ask(page, "这个问题涉及哪些学生？");
    await expect(page.locator("#chatMessages")).toContainText("请先选择", { timeout: 15000 });
    await expect(page.locator("#chatMessages")).not.toContainText("001");
    await expect(page.locator("#chatMessages")).not.toContainText("002");
    expect(errors.serverErrors).toHaveLength(0);
  });

  test("AI-08 完整教师 10 分钟体验", async ({ page }) => {
    const errors = collectErrors(page);
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="teacherToday"]').click();
    await expect(page.locator("#todayTeachingContent .issue-card").first()).toBeVisible({ timeout: 15000 });
    await page.locator("#todayTeachingContent .issue-card").first().click();
    await page.locator(".issue-drawer-close").click();
    await page.locator("#closeWorkspace").click();

    await ask(page, "为什么？");
    await expect(page.locator("#chatMessages")).toContainText("学生", { timeout: 15000 });
    await ask(page, "那应该怎么教？");
    await expect(page.locator("#chatMessages .ai-action-btn", { hasText: "生成方案" })).toBeVisible();
    await page.locator("#chatMessages .ai-action-btn", { hasText: "生成方案" }).click();
    await expect(page.locator("#issueDetailDrawer .candidate-card").first()).toBeVisible({ timeout: 15000 });
    await page.locator("#issueDetailDrawer .candidate-adopt").first().click();
    await page.getByRole("button", { name: "让 AI 调整" }).click();
    await ask(page, "改成20分钟，并把001单独安排。");
    await expect(page.locator("#chatMessages")).toContainText("20 分钟", { timeout: 15000 });
    await page.locator("#chatMessages .ai-action-btn", { hasText: "采用方案" }).click();
    await page.getByRole("button", { name: "采用此方案" }).click();
    await expect(page.locator("#issueDetailDrawer")).toContainText("方案已保存", { timeout: 15000 });

    expect(errors.pageErrors).toHaveLength(0);
    expect(errors.serverErrors).toHaveLength(0);
  });
});
