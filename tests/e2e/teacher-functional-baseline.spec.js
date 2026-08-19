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
let commentId = null;

async function loginTeacher(ctx) {
  const resp = await ctx.post("/api/auth/login", {
    data: { username: "000", password: "123456" },
  });
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  expect(body.token).toBeTruthy();
  return body.token;
}

async function createClass(ctx, token, name, jobRole = JOB_ROLE) {
  const resp = await ctx.post("/api/teacher/classes", {
    headers: { Authorization: `Bearer ${token}` },
    data: { name, job_role: jobRole, term: "2026-baseline" },
  });
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  expect(body.class?.id).toBeTruthy();
  return body.class;
}

async function addStudents(ctx, token, classId, usernames) {
  const resp = await ctx.post(`/api/teacher/classes/${classId}/students`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { student_usernames: usernames },
  });
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  expect(body.ok).toBeTruthy();
}

async function archiveClass(ctx, token, classId) {
  await ctx.post(`/api/teacher/classes/${classId}/archive`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

async function archiveClassesByPrefix(ctx, token, prefix) {
  const resp = await ctx.get("/api/teacher/classes", {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(resp.ok()).toBeTruthy();
  const body = await resp.json();
  for (const cls of body.classes || []) {
    if (String(cls.name || "").startsWith(prefix)) {
      await archiveClass(ctx, token, cls.id);
    }
  }
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
            "source": "playwright_teacher_baseline",
        })
    append_session_event(session_id, {
        "event_type": "question_explained",
        "ability_id": "pl_program_monitor",
        "source": "playwright_teacher_baseline",
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

async function selectClass(page, name) {
  await page.locator("#teacherClassLabel").click();
  await expect(page.locator("#classDropdown")).toBeVisible();
  await page.locator(".class-dropdown-item", { hasText: name }).first().click();
  await expect(page.locator("#teacherClassLabel")).toContainText(name);
}

async function expectGraphRendered(page, selector) {
  await expect(page.locator(selector)).toBeVisible();
  await page.waitForFunction((sel) => {
    const root = document.querySelector(sel);
    return !!root && root.querySelectorAll("svg .node").length > 0;
  }, selector);
}

test.beforeAll(async () => {
  const stamp = Date.now();
  createdPrefix = `E2E-FB-${stamp}`;
  classAName = `${createdPrefix}-A`;
  classBName = `${createdPrefix}-B`;

  const ctx = await request.newContext({ baseURL: BASE_URL });
  teacherToken = await loginTeacher(ctx);

  classA = await createClass(ctx, teacherToken, classAName, JOB_ROLE);
  classB = await createClass(ctx, teacherToken, classBName, "mechanical_electrical_maintenance_worker");
  await addStudents(ctx, teacherToken, classA.id, ["001", "002"]);
  await addStudents(ctx, teacherToken, classB.id, ["006", "007"]);

  seedTeacherEvidence(JOB_ROLE, ["001", "002"]);

  const commentResp = await ctx.post("/api/teacher/comments/generate", {
    headers: { Authorization: `Bearer ${teacherToken}` },
    data: { student_id: "001", class_id: classA.id, job_role: JOB_ROLE },
  });
  expect(commentResp.ok()).toBeTruthy();
  const commentBody = await commentResp.json();
  expect(commentBody.ok).toBeTruthy();
  commentId = commentBody.comment?.id;
  expect(commentId).toBeTruthy();

  await ctx.dispose();
});

test.afterAll(async () => {
  if (!teacherToken || !createdPrefix) return;
  const ctx = await request.newContext({ baseURL: BASE_URL });
  await archiveClassesByPrefix(ctx, teacherToken, createdPrefix);
  await ctx.dispose();
});

test("teacher functional baseline UI flows are usable", async ({ page }) => {
  test.setTimeout(90000);
  const errors = collectErrors(page);
  const dialogs = [];
  page.on("dialog", async (dialog) => {
    dialogs.push(dialog.message());
    await dialog.accept();
  });

  await loginAsTeacher(page, "000", "123456");

  await page.locator("#createClassBtn").click();
  await expect(page.locator("#createClassModal")).toBeVisible();
  await page.locator("#newClassName").fill(`${createdPrefix}-UI`);
  await page.locator("#newClassTerm").fill("2026-ui");
  await page.locator("#createClassModal .btn-primary").click();
  await expect(page.locator("#createClassModal")).toBeHidden();
  await expect(page.locator("#teacherClassLabel")).toContainText(`${createdPrefix}-UI`);

  await selectClass(page, classAName);

  await expect(page.locator("#todayTeachingContent .issue-card").first()).toBeVisible({ timeout: 15000 });
  await expect(page.locator("#todayTeachingContent")).toContainText("2 人");
  await page.locator("#todayTeachingContent .issue-card").first().click();
  await expect(page.locator("#issueDetailDrawer")).toHaveClass(/open/);
  await expect(page.locator("#issueDetailDrawer")).toContainText("主要能力");
  await expect(page.locator("#issueDetailDrawer .student-chip", { hasText: "001" })).toBeVisible();

  const candidatesResponse = page.waitForResponse((resp) =>
    resp.url().includes("/api/v2/teacher/issues/candidates") && resp.status() === 200
  );
  await page.getByRole("button", { name: "生成干预方案" }).click();
  await candidatesResponse;
  await expect(page.locator("#issueDetailDrawer")).toContainText("Intervention Candidates");
  await expect(page.locator("#issueDetailDrawer .candidate-card").first()).toBeVisible();
  await page.locator(".issue-drawer-close").click();
  await expect(page.locator("#issueDetailDrawer")).not.toHaveClass(/open/);

  await page.locator("#manageClassBtn").click();
  await expect(page.locator("#manageStudentsModal")).toBeVisible();
  await page.locator("#studentSearchInput").fill("003");
  await expect(page.locator("#studentManageList .student-manage-row", { hasText: "003" }).first()).toBeVisible();
  await page.locator('#studentManageList .student-manage-check[data-username="003"]').check();
  await page.getByRole("button", { name: "加入班级" }).click();
  await expect.poll(() => dialogs.length).toBeGreaterThan(0);
  await expect(page.locator("#studentManageList .student-manage-row", { hasText: "003" })).toContainText("已在本班");

  await page.locator('#studentManageList .student-manage-check[data-username="003"]').check();
  await page.getByRole("button", { name: "移除选中" }).click();
  await expect.poll(() => dialogs.some((message) => message.includes("Removed"))).toBeTruthy();
  await page.locator("#studentSearchInput").fill("003");
  await expect(page.locator("#studentManageList .student-manage-row", { hasText: "003" })).not.toContainText("已在本班");
  await page.locator("#manageStudentsModal .modal-close").click();
  await expect(page.locator("#manageStudentsModal")).toBeHidden();

  await page.locator('.teacher-nav-tab[data-tab="students"]').click();
  await expect(page.locator("#teacherStudentListPane .student-card", { hasText: "001" }).first()).toBeVisible();
  await expect(page.locator("#teacherStudentListPane .student-card", { hasText: "006" })).toHaveCount(0);
  await page.locator('#teacherStudentListPane .student-card[data-student-id="001"]').click();
  await expect(page.locator("#teacherStudentDetailPane")).toContainText("弱项");
  await expect(page.locator("#teacherStudentDetailPane")).toContainText("sn_type_identify");

  await page.locator('.teacher-nav-tab[data-tab="insights"]').click();
  await expect(page.locator("#tw-insights")).toContainText("班级洞察");
  await expect(page.locator("#tw-insights")).toContainText("班级最薄弱能力");
  await expect(page.locator("#tw-insights")).toContainText("传感器类型识别");
  await expectGraphRendered(page, "#teacherClassGraphDiagram");

  await page.locator('.teacher-nav-tab[data-tab="standards"]').click();
  await expect(page.locator("#tw-standards")).toContainText("岗位标准");
  await expect(page.locator("#tw-standards")).toContainText("nodes");
  await expectGraphRendered(page, "#teacherJobGraphDiagram");
  await page.getByRole("button", { name: "更新建议" }).click();
  await expect(page.locator("#tw-standards")).toContainText(/更新建议|暂无待审核更新建议/);
  await page.getByRole("button", { name: "版本" }).click();
  await expect(page.locator("#tw-standards")).toContainText(/版本|暂无版本记录/);
  await page.getByRole("button", { name: "当前图谱" }).click();
  await expectGraphRendered(page, "#teacherJobGraphDiagram");

  await page.locator('.teacher-nav-tab[data-tab="feedback"]').click();
  await expect(page.locator("#tw-feedback")).toContainText("教学反馈");
  await page.getByRole("button", { name: /草稿/ }).click();
  await expect(page.locator("#tw-feedback .comment-card").first()).toBeVisible();
  await page.locator("#tw-feedback .comment-card").first().click();
  await expect(page.locator("#tw-feedback")).toContainText("评语详情");
  await expect(page.locator("#tw-feedback")).toContainText("draft");
  await page.getByRole("button", { name: "审核" }).click();
  await expect(page.locator("#tw-feedback")).toContainText("reviewed");
  await page.getByRole("button", { name: "发布" }).click();
  await expect(page.locator("#tw-feedback")).toContainText("published");
  await page.getByRole("button", { name: "返回列表" }).click();
  await page.getByRole("button", { name: /草稿/ }).click();
  expect(await page.evaluate(() => window.TeacherUI?._commentFilter)).toBe("draft");
  await selectClass(page, classBName);
  expect(await page.evaluate(() => window.TeacherUI?._commentFilter)).toBe("all");
  await expect(page.locator("#tw-feedback")).toContainText("教学反馈");

  await selectClass(page, classAName);
  await page.locator("#copilotInput").fill("查看学生 008 的学习状态");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.locator("#teacherChatMessages")).toContainText("不属于当前班级", { timeout: 15000 });

  const fit = await page.evaluate(() => {
    const required = [".teacher-layout", ".teacher-copilot", ".teacher-workspace"]
      .map((selector) => {
        const el = document.querySelector(selector);
        if (!el) return { selector, missing: true };
        const rect = el.getBoundingClientRect();
        return {
          selector,
          missing: false,
          left: rect.left,
          right: rect.right,
          top: rect.top,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        };
      });
    return {
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
      canScrollX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      required,
    };
  });
  expect(fit.canScrollX).toBeFalsy();
  expect(fit.required.filter((item) => item.missing || item.width <= 0 || item.height <= 0)).toEqual([]);

  await page.screenshot({
    path: "test-results/teacher-functional-baseline-desktop.png",
    fullPage: false,
  });

  expect(errors.pageErrors).toHaveLength(0);
  expect(errors.serverErrors).toHaveLength(0);
});
