import { test, expect, request } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { collectErrors, loginAsTeacher } from "./helpers/auth.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const BASE_URL = "http://127.0.0.1:8765";
const JOB_ROLE = "automation_line_commissioning_maintenance_newcomer";
const ROBOT_JOB_ROLE = "industrial_robot_maintenance";

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
    data: { name, job_role: jobRole, term: "2026-practicality" },
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

function seedTeacherEvidence(jobRole, students, abilityId) {
  const script = `
import json
import os
import time
from app.services.assessment_store import save_state
from app.services.feedback import append_session_event

job_role = os.environ["E2E_JOB_ROLE"]
students = json.loads(os.environ["E2E_STUDENTS"])
ability_id = os.environ["E2E_ABILITY_ID"]
now = time.time()

for username in students:
    session_id = f"{job_role}-{username}"
    for i in range(4):
        append_session_event(session_id, {
            "event_type": "initial_quiz_answered",
            "ability_id": ability_id,
            "is_correct": False,
            "source": "playwright_teacher_practicality",
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
            "weak_abilities": [ability_id],
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
      E2E_ABILITY_ID: abilityId,
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

async function openTodayAndIssue(page) {
  await page.locator('[data-workspace-panel="teacherToday"]').click();
  await expect(page.locator("#todayTeachingContent .issue-card").first()).toBeVisible({ timeout: 15000 });
  await page.locator("#todayTeachingContent .issue-card").first().click();
  await expect(page.locator("#issueDetailDrawer")).toHaveClass(/open/);
}

test.describe.serial("Teacher Practicality Pass V1", () => {
  test.beforeAll(async () => {
    const stamp = Date.now();
    createdPrefix = `E2E-TP-${stamp}`;
    classAName = `${createdPrefix}-A`;
    classBName = `${createdPrefix}-B`;

    const ctx = await request.newContext({ baseURL: BASE_URL });
    teacherToken = await loginTeacher(ctx);
    classA = await createClass(ctx, teacherToken, classAName, JOB_ROLE);
    classB = await createClass(ctx, teacherToken, classBName, ROBOT_JOB_ROLE);
    await addStudents(ctx, teacherToken, classA.id, ["001", "002"]);
    await addStudents(ctx, teacherToken, classB.id, ["006", "007"]);
    seedTeacherEvidence(JOB_ROLE, ["001", "002"], "sn_type_identify");
    seedTeacherEvidence(ROBOT_JOB_ROLE, ["006", "007"], "ir_06");
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

  test("TP-01 登录教师", async ({ page }) => {
    const errors = collectErrors(page);
    await loginAsTeacher(page);
    await expect(page.locator("body")).toHaveAttribute("data-role", "teacher");
    await expect(page.locator(".launcher-panel.role-teacher")).toBeVisible();
    expect(errors.serverErrors).toHaveLength(0);
  });

  test("TP-02 全局班级", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    for (const panel of ["teacherToday", "classInsights", "studentMgmt", "teacherComments", "teacherJobGraph"]) {
      await page.locator(`[data-workspace-panel="${panel}"]`).click();
      await expect(page.locator("#teacherClassLabel")).toContainText(classAName);
      await expect(page.locator("#teacherClassMeta")).toBeVisible();
    }
  });

  test("TP-03 岗位同步", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classBName);
    await expect(page.locator("#teacherClassMeta")).toContainText("工业机器人系统运维员");
    await page.locator('[data-workspace-panel="teacherJobGraph"]').click();
    await expect(page.locator("#jobAdminRole")).toHaveValue("工业机器人系统运维员");
    const context = await page.evaluate(() => ({
      jobRole: window.TeacherUI?.currentClass?.job_role,
      aiJobRole: window.TeacherUI?.aiContext?.job_role,
    }));
    expect(context.jobRole).toBe(ROBOT_JOB_ROLE);
    expect(context.aiJobRole).toBe(ROBOT_JOB_ROLE);
  });

  test("TP-04 导航", async ({ page }) => {
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

  test("TP-05 今日教学", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="teacherToday"]').click();
    await expect(page.locator("#todayTeachingContent .issue-card").first()).toBeVisible({ timeout: 15000 });
    const today = page.locator("#todayTeachingContent");
    await expect(today).toContainText("优先处理");
    await expect(today).toContainText("名学生受到影响");
    await expect(today).toContainText("主要能力");
    const text = await today.innerText();
    for (const word of ["high", "mid", "low", "sn_type_identify"]) {
      expect(text).not.toContain(word);
    }
  });

  test("TP-06 AI 行为", async ({ page }) => {
    const errors = collectErrors(page);
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await openTodayAndIssue(page);
    const responsePromise = page.waitForResponse((resp) =>
      resp.url().includes("/api/teacher/assistant/message") && resp.status() === 200
    );
    await page.locator("#issueDetailDrawer").getByRole("button", { name: "AI 分析原因" }).click();
    await responsePromise;
    await expect(page.locator("#chatMessages")).toContainText("学生", { timeout: 15000 });
    expect(errors.serverErrors).toHaveLength(0);
  });

  test("TP-07 调整方案", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await openTodayAndIssue(page);
    await page.getByRole("button", { name: "生成干预方案" }).click();
    await expect(page.locator("#issueDetailDrawer .candidate-card").first()).toBeVisible({ timeout: 15000 });
    await page.locator("#issueDetailDrawer .candidate-adopt").first().click();
    await page.locator("#issueDetailDrawer").getByRole("button", { name: "让 AI 调整" }).click();
    await expect(page.locator("#chatInput")).not.toHaveValue(/001/);
  });

  test("TP-08 跨岗位方案", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classBName);
    const plans = await page.evaluate(() => {
      const robot = window.TeacherUI.candidatePlan(
        { candidate_id: "robot", ability_ids: ["ir_06"], target_students: ["006", "007"] },
        { issue_id: "robot-tcp", title: "TCP 标定薄弱" },
        ["006", "007"]
      );
      const sensor = window.TeacherUI.candidatePlan(
        { candidate_id: "sensor", ability_ids: ["sn_type_identify"], target_students: ["001", "002"] },
        { issue_id: "sensor-type", title: "传感器类型识别薄弱" },
        ["001", "002"]
      );
      return { robot, sensor };
    });
    expect(JSON.stringify(plans.robot)).not.toContain("NPN");
    expect(JSON.stringify(plans.robot)).not.toContain("PNP");
    expect(JSON.stringify(plans.robot)).not.toContain("PLC");
    expect(JSON.stringify(plans.robot)).not.toContain("传感器");
    expect(JSON.stringify(plans.sensor)).toContain("NPN/PNP");
  });

  test("TP-09 班级洞察", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="classInsights"]').click();
    await expect(page.locator("#tw-insights")).toContainText("薄弱比例", { timeout: 15000 });
    await expect(page.locator("#tw-insights")).toContainText("平均掌握度");
    await expect(page.locator("#tw-insights .teacher-progress-risk").first()).toBeVisible();
  });

  test("TP-10 学生页", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="studentMgmt"]').click();
    await expect(page.locator('#teacherStudentListPane .student-card[data-student-id="001"]').first()).toBeVisible({ timeout: 15000 });
    await page.locator('#teacherStudentListPane .student-card[data-student-id="001"]').click();
    await expect(page.locator('#teacherStudentListPane .student-card[data-student-id="001"]')).toHaveClass(/active/);
    await expect(page.locator("#teacherStudentDetailPane")).toContainText("主要薄弱");
    await expect(page.locator("#teacherStudentDetailPane")).toContainText("传感器类型识别");
    const text = await page.locator("#teacherStudentDetailPane").innerText();
    for (const word of ["events", "Loading student", "sn_type_identify"]) {
      expect(text).not.toContain(word);
    }
  });

  test("TP-11 教学反馈", async ({ page }) => {
    await loginAsTeacher(page);
    await selectClass(page, classAName);
    await page.locator('[data-workspace-panel="teacherComments"]').click();
    await expect(page.locator("#tw-feedback .comment-card").first()).toBeVisible({ timeout: 15000 });
    const text = await page.locator("#tw-feedback").innerText();
    expect(text).toContain("草稿");
    for (const word of ["draft", "reviewed", "published"]) {
      expect(text).not.toContain(word);
    }
  });

  test("TP-12 操作反馈", async ({ page }) => {
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
    await page.locator("#studentSearchInput").fill("003");
    await page.locator('#studentManageList .student-manage-check[data-username="003"]').check();
    await page.getByRole("button", { name: "移除选中" }).click();
    await expect(page.locator(".teacher-toast-success").last()).toContainText("已移除");
    expect(dialogs).toHaveLength(0);
  });
});
