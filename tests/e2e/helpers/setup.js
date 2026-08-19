// tests/e2e/helpers/setup.js
import { request } from "@playwright/test";

let teacherToken = null;

export async function getTeacherToken() {
  if (teacherToken) return teacherToken;
  const ctx = await request.newContext({ baseURL: "http://127.0.0.1:8765" });
  const resp = await ctx.post("/api/auth/login", {
    data: { username: "000", password: "123456" },
  });
  const data = await resp.json();
  teacherToken = data.token;
  await ctx.dispose();
  return teacherToken;
}

export async function apiCreateClass(token, name, jobRole) {
  const ctx = await request.newContext({ baseURL: "http://127.0.0.1:8765" });
  const resp = await ctx.post("/api/teacher/classes", {
    headers: { Authorization: `Bearer ${token}` },
    data: { name, job_role: jobRole },
  });
  const data = await resp.json();
  await ctx.dispose();
  return data.class?.id || null;
}

export async function apiAddStudents(token, classId, usernames) {
  const ctx = await request.newContext({ baseURL: "http://127.0.0.1:8765" });
  const resp = await ctx.post(`/api/teacher/classes/${classId}/students`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { student_usernames: usernames },
  });
  const data = await resp.json();
  await ctx.dispose();
  return data;
}

export async function apiListClasses(token) {
  const ctx = await request.newContext({ baseURL: "http://127.0.0.1:8765" });
  const resp = await ctx.get("/api/teacher/classes", {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await resp.json();
  await ctx.dispose();
  return data.classes || [];
}
