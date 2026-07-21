import { chromium } from "playwright";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const PORT = 8794;
const BASE = `http://127.0.0.1:${PORT}`;

const server = spawn("python3", ["-m", "http.server", String(PORT), "--directory", path.join(ROOT, "static")], { stdio: "ignore" });
const browser = await chromium.launch({
  headless: true,
  args: [
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    `--use-file-for-fake-audio-capture=${path.join(ROOT, "tests/fixtures/voice-ko/01.wav")}`,
  ],
});

const results = [];
function pass(name, detail = {}) {
  results.push({ name, result: "pass", ...detail });
}
async function waitForCount(page, getCount, expected) {
  await page.waitForFunction(({ getCountSource, expectedCount }) => {
    return Function(`return (${getCountSource})`)()() >= expectedCount;
  }, { getCountSource: getCount.toString(), expectedCount: expected }, { timeout: 5000 });
}
async function makePage({
  transcript = "로컬 음성 전사",
  chatFailure = false,
  chatFailureStatus = 500,
  chatFailureCode = "provider_unavailable",
  ttsFailure = false,
  transcribeFailureStatus = 0,
  transcribeFailureCode = "provider_unavailable",
  networkDenied = false,
  delayedTranscribe = false,
} = {}) {
  const context = await browser.newContext({ permissions: ["microphone"] });
  const page = await context.newPage();
  const counts = { transcribe: 0, chat: [], synthesize: 0 };
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.addInitScript(() => {
    window.__revokedUrls = [];
    const originalRevoke = URL.revokeObjectURL.bind(URL);
    URL.revokeObjectURL = (url) => { window.__revokedUrls.push(url); originalRevoke(url); };
    window.Audio = class {
      play() { return Promise.resolve(); }
      pause() {}
      removeAttribute() {}
    };
  });
  await page.route("**/api/config", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ mode: "coaching", voice: { enabled: true } }),
  }));
  await page.route("**/api/voice/transcribe", async (route) => {
    counts.transcribe += 1;
    if (networkDenied) {
      await route.abort("failed");
      return;
    }
    if (transcribeFailureStatus) {
      await route.fulfill({
        status: transcribeFailureStatus,
        contentType: "application/json",
        body: JSON.stringify({ error_code: transcribeFailureCode }),
      });
      return;
    }
    if (delayedTranscribe) await sleep(300);
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ text: transcript }) });
  });
  await page.route("**/api/chat", async (route) => {
    counts.chat.push(JSON.parse(route.request().postData() || "{}"));
    if (chatFailure && counts.chat.length === 1) {
      await route.fulfill({
        status: chatFailureStatus,
        contentType: "application/json",
        body: JSON.stringify({ error_code: chatFailureCode, detail: "fake chat failure" }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ reply: "확인된 응답입니다.", turn: 1, session_token: "fake-session-token", intake: null }) });
  });
  await page.route("**/api/voice/synthesize", async (route) => {
    counts.synthesize += 1;
    if (ttsFailure) {
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error_code: "provider_unavailable" }) });
      return;
    }
    await route.fulfill({ status: 200, contentType: "audio/wav", body: Buffer.from("RIFFfake-wav") });
  });
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("#voice-controls:not([hidden])", { timeout: 5000 });
  return { page, context, counts, pageErrors };
}
async function record(page) {
  await page.locator("#voice-toggle").click();
  await page.waitForFunction(() => document.querySelector("#voice-toggle").getAttribute("aria-pressed") === "true", null, { timeout: 5000 });
  await sleep(950);
  await page.locator("#voice-toggle").click();
  await page.waitForSelector("#voice-review:not([hidden])", { timeout: 7000 });
}

try {
  const success = await makePage({});
  await success.page.locator("#message-input").fill("미리 입력한 텍스트");
  await record(success.page);
  if (success.counts.chat.length !== 0) throw new Error("/api/chat called before transcript confirmation");
  if (await success.page.locator("#message-input").inputValue() !== "미리 입력한 텍스트") throw new Error("typed input was not preserved");
  pass("zero chat before confirmation", { chat_calls: 0 });
  await success.page.locator("#voice-edit").click();
  await success.page.locator("#voice-transcript").fill("수정한 음성 내용");
  await success.page.locator("#voice-send").click();
  await waitForCount(success.page, () => document.querySelectorAll(".message-row-user").length, 1);
  if (success.counts.chat.length !== 1 || success.counts.chat[0].message !== "수정한 음성 내용") throw new Error("confirmed payload changed or duplicated");
  pass("one canonical chat after confirmation", { chat_calls: success.counts.chat.length, message: success.counts.chat[0].message });
  await success.page.waitForSelector(".tts-button", { timeout: 5000 });
  await success.page.locator(".tts-button").click();
  await success.page.waitForFunction(() => document.querySelector(".tts-button").textContent === "응답 중지", null, { timeout: 5000 });
  await success.page.locator(".tts-button").click();
  await waitForCount(success.page, () => window.__revokedUrls.length, 1);
  pass("tts synthesize then revoke", { synthesize_calls: success.counts.synthesize, revoked_urls: await success.page.evaluate(() => window.__revokedUrls.length) });
  await success.context.close();

  const overlong = await makePage({ transcript: "가".repeat(2001) });
  await record(overlong.page);
  if (!(await overlong.page.locator("#voice-truncation-warning").isVisible())) throw new Error("overlong warning not visible");
  await overlong.page.locator("#voice-send").click();
  await waitForCount(overlong.page, () => document.querySelectorAll(".message-row-user").length, 1);
  if (overlong.counts.chat[0].message.length !== 2000) throw new Error("overlong confirmed message was not bounded");
  pass("overlong transcript warning and explicit confirmation", { transcript_length: 2001, sent_length: 2000 });
  await overlong.context.close();

  const retry = await makePage({ chatFailure: true });
  await record(retry.page);
  const confirmed = await retry.page.locator("#voice-transcript").inputValue();
  await retry.page.locator("#voice-send").click();
  await retry.page.waitForFunction(() => document.querySelector("#voice-review-status").textContent.includes("전송에 실패"), null, { timeout: 5000 });
  if (await retry.page.locator("#voice-transcript").inputValue() !== confirmed) throw new Error("chat error did not preserve transcript");
  pass("chat error preserves confirmed transcript", { chat_calls: retry.counts.chat.length });
  await retry.context.close();

  for (const failure of [
    { name: "chat-429", status: 429, code: "provider_unavailable" },
    { name: "chat-401", status: 401, code: "session_auth_required" },
  ]) {
    const page = await makePage({
      chatFailure: true,
      chatFailureStatus: failure.status,
      chatFailureCode: failure.code,
    });
    await record(page.page);
    const confirmed = await page.page.locator("#voice-transcript").inputValue();
    await page.page.locator("#voice-send").click();
    await page.page.waitForFunction(() => document.querySelector("#voice-review-status").textContent.includes("전송에 실패"), null, { timeout: 5000 });
    if (await page.page.locator("#voice-transcript").inputValue() !== confirmed) throw new Error(`${failure.name} dropped transcript`);
    if (page.counts.chat.length !== 1) throw new Error(`${failure.name} duplicated chat request`);
    if (page.pageErrors.length) throw new Error(`${failure.name} uncaught page error: ${page.pageErrors.join(" | ")}`);
    pass(`${failure.name} preserves review and avoids duplicate chat`, { status: failure.status, chat_calls: page.counts.chat.length });
    await page.context.close();
  }

  const ttsError = await makePage({ ttsFailure: true });
  await record(ttsError.page);
  await ttsError.page.locator("#voice-send").click();
  await ttsError.page.waitForSelector(".tts-button", { timeout: 5000 });
  await ttsError.page.locator(".tts-button").click();
  await ttsError.page.waitForFunction(() => document.querySelector(".tts-status").textContent.includes("텍스트로"), null, { timeout: 5000 });
  if (!(await ttsError.page.locator(".message-row-assistant").last().textContent()).includes("확인된 응답")) throw new Error("assistant bubble disappeared after TTS error");
  pass("tts error keeps assistant text", { synthesize_calls: ttsError.counts.synthesize });
  await ttsError.context.close();

  for (const failure of [
    { name: "sidecar-absent", options: { transcribeFailureStatus: 503, transcribeFailureCode: "provider_unavailable" } },
    { name: "network-denied", options: { networkDenied: true } },
  ]) {
    const page = await makePage(failure.options);
    await page.page.locator("#voice-toggle").click();
    await page.page.waitForFunction(() => document.querySelector("#voice-toggle").getAttribute("aria-pressed") === "true", null, { timeout: 5000 });
    await sleep(950);
    await page.page.locator("#voice-toggle").click();
    await page.page.waitForFunction(() => document.querySelector("#voice-status").textContent.includes("사용할 수 없") || document.querySelector("#voice-status").textContent.includes("연결하지 못"), null, { timeout: 7000 });
    if (page.counts.chat.length !== 0) throw new Error(`${failure.name} called /api/chat`);
    if (page.pageErrors.length) throw new Error(`${failure.name} uncaught page error: ${page.pageErrors.join(" | ")}`);
    pass(`${failure.name} fails closed with text path intact`, { transcribe_calls: page.counts.transcribe, chat_calls: 0 });
    await page.context.close();
  }

  const stale = await makePage({ delayedTranscribe: true });
  await stale.page.locator("#voice-toggle").click();
  await stale.page.waitForFunction(() => document.querySelector("#voice-toggle").getAttribute("aria-pressed") === "true", null, { timeout: 5000 });
  await sleep(950);
  await stale.page.locator("#voice-toggle").click();
  await stale.page.waitForTimeout(50);
  await stale.page.locator("#reset-session").click();
  await sleep(450);
  if (!(await stale.page.locator("#voice-review").isHidden())) throw new Error("stale callback restored review after reset");
  if (stale.pageErrors.length) throw new Error(`stale reset uncaught page error: ${stale.pageErrors.join(" | ")}`);
  pass("reset blocks stale transcription callback");
  await stale.context.close();
  for (const item of [success, overlong, retry, ttsError]) {
    if (item.pageErrors.length) throw new Error(`uncaught page error: ${item.pageErrors.join(" | ")}`);
  }
  console.log(JSON.stringify({ task: "T8", result: "pass", scenarios: results, generated_artifacts: [] }));
} finally {
  await browser.close().catch(() => {});
  server.kill("SIGTERM");
}
