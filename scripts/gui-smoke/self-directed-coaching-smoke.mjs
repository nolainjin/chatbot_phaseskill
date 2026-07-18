import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const PORT = 8964;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const shot = path.join(process.cwd(), "screenshots", "self-directed-coaching.png");
fs.mkdirSync(path.dirname(shot), { recursive: true });
const server = spawn(
  ".venv/bin/python",
  ["-m", "uvicorn", "app.main:app", "--port", String(PORT)],
  { cwd: REPO_ROOT, env: { ...process.env, MODEL: "fake", KNOWLEDGE_DIR: "knowledge-self-directed" }, stdio: "ignore" },
);
try {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    try {
      if ((await fetch(`${BASE_URL}/api/config`)).ok) break;
    } catch {}
    await sleep(250);
  }
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  if (!(await page.isHidden("#stepper")) || !(await page.isHidden("#intake-panel")) || !(await page.isHidden("#coaching-status"))) {
    throw new Error("coaching UI did not start fail-closed");
  }
  await page.fill("#message-input", "계획은 세웠지만 시작 버튼을 누르지 못했어요.");
  await page.click("#send-button");
  await page.waitForSelector("#coaching-status:not([hidden])", { timeout: 15000 });
  if (!(await page.locator("#coaching-stage").textContent()) || !(await page.locator("#coaching-next-action").textContent())) {
    throw new Error("coaching stage/action was not rendered");
  }
  const text = await page.locator("#coaching-status").textContent();
  if (/LearningState|bottleneck|SYSTEM_INSTRUCTIONS|prompt/.test(text)) {
    throw new Error("internal coaching state leaked into UI");
  }
  await page.screenshot({ path: shot });
  await browser.close();
  console.log("PASS self-directed coaching UI smoke");
} finally {
  server.kill("SIGTERM");
}
