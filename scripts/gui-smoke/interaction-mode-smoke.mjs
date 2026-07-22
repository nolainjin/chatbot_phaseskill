import { strict as assert } from "node:assert";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

import { chromium } from "playwright";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const STATIC_ROOT = path.join(ROOT, "static");
const SCREENSHOT_PATH = path.join(ROOT, ".omo/evidence/task-6-chat-voice-dual-mode.png");
const scenarioIndex = process.argv.indexOf("--scenario");
const requestedScenario = scenarioIndex === -1 ? "all" : process.argv[scenarioIndex + 1];
const targetedScenarios = new Set([
  "switch-during-recording",
  "switch-during-transcribe",
  "switch-after-confirm",
  "autoplay-blocked",
  "unsupported-reload",
]);
assert.ok(requestedScenario === "all" || targetedScenarios.has(requestedScenario), `unknown scenario: ${requestedScenario}`);

let staticServer = null;
let baseUrl = process.env.INTERACTION_MODE_BASE_URL || "";
if (!baseUrl) {
  staticServer = createServer(async (request, response) => {
    try {
      const url = new URL(request.url || "/", "http://127.0.0.1");
      const pathname = url.pathname === "/" ? "/index.html" : decodeURIComponent(url.pathname);
      const filePath = path.resolve(STATIC_ROOT, `.${pathname}`);
      if (!filePath.startsWith(`${STATIC_ROOT}${path.sep}`)) {
        response.writeHead(403).end("forbidden");
        return;
      }
      const body = await readFile(filePath);
      const contentType = filePath.endsWith(".html")
        ? "text/html; charset=utf-8"
        : filePath.endsWith(".css")
          ? "text/css; charset=utf-8"
          : "text/javascript; charset=utf-8";
      response.writeHead(200, { "Content-Type": contentType, "Cache-Control": "no-store" });
      response.end(body);
    } catch {
      response.writeHead(404).end("not found");
    }
  });
  await new Promise((resolve, reject) => {
    staticServer.once("error", reject);
    staticServer.listen(0, "127.0.0.1", resolve);
  });
  const address = staticServer.address();
  assert.ok(address && typeof address === "object", "ephemeral static server address is available");
  baseUrl = `http://127.0.0.1:${address.port}`;
}
const BASE_URL = baseUrl;

const browser = await chromium.launch({ headless: true });
const results = [];

function pass(name, detail = {}) {
  results.push({ name, result: "pass", ...detail });
}

function responseBody(turn, options = {}) {
  return {
    reply: options.reply || `검증 응답 ${turn}`,
    turn,
    session_token: `session-token-${turn}`,
    intake: options.intake ?? null,
    coach_stage: "탐색",
    next_action: "다음 질문 확인",
  };
}

async function createFixture(options = {}) {
  const context = await browser.newContext();
  const page = await context.newPage();
  const pageErrors = [];
  const requests = [];
  const pendingChats = [];
  const pendingTranscriptions = [];
  const counts = { config: 0, transcribe: 0, chat: 0, synthesize: 0 };
  const supportVoice = options.supportVoice !== false;
  const storedMode = options.storedMode || "";
  const audioMode = options.audioMode || "allowed";
  const permissionMode = options.permissionMode || "immediate";
  const configVoice = options.configVoice !== false;

  page.on("pageerror", (error) => pageErrors.push(error.message));
  await context.addInitScript(({ supportVoice: enabled, storedMode: initialMode, audioMode: playbackMode, permissionMode: mediaMode }) => {
    sessionStorage.setItem("lmwiki_session_id", "interaction-mode-session");
    if (initialMode) sessionStorage.setItem("lmwiki_interaction_mode", initialMode);
    window.__interactionQa = {
      audioPlayCalls: 0,
      getUserMediaCalls: 0,
      tracks: [],
      resolvePermission: null,
    };

    class FakeTrack extends EventTarget {
      constructor() {
        super();
        this.stopped = false;
      }

      stop() {
        this.stopped = true;
      }
    }

    class FakeStream extends EventTarget {
      constructor() {
        super();
        this.track = new FakeTrack();
        window.__interactionQa.tracks.push(this.track);
      }

      getTracks() {
        return [this.track];
      }
    }

    class FakeMediaRecorder {
      static isTypeSupported(value) {
        return value === "audio/webm;codecs=opus";
      }

      constructor(stream, recorderOptions = {}) {
        this.stream = stream;
        this.mimeType = recorderOptions.mimeType || "audio/webm";
        this.state = "inactive";
        this.onstart = null;
        this.onstop = null;
        this.ondataavailable = null;
        this.onerror = null;
      }

      start() {
        this.state = "recording";
        queueMicrotask(() => this.onstart?.());
      }

      stop() {
        this.state = "inactive";
        queueMicrotask(() => {
          this.ondataavailable?.({ data: new Blob([new Uint8Array(512)], { type: this.mimeType }) });
          this.onstop?.();
        });
      }
    }

    class FakeAudio {
      constructor() {
        this.onended = null;
        this.onerror = null;
      }

      play() {
        window.__interactionQa.audioPlayCalls += 1;
        if (playbackMode === "blocked" && window.__interactionQa.audioPlayCalls === 1) {
          return Promise.reject(Object.assign(new Error("blocked"), { name: "NotAllowedError" }));
        }
        if (playbackMode === "failed") return Promise.reject(new Error("playback failed"));
        queueMicrotask(() => this.onended?.());
        return Promise.resolve();
      }

      pause() {}
      removeAttribute() {}
    }

    window.Audio = FakeAudio;
    if (enabled) {
      Object.defineProperty(window, "MediaRecorder", { configurable: true, value: FakeMediaRecorder });
      Object.defineProperty(navigator, "mediaDevices", {
        configurable: true,
        value: {
          getUserMedia() {
            window.__interactionQa.getUserMediaCalls += 1;
            const stream = new FakeStream();
            if (mediaMode !== "deferred") return Promise.resolve(stream);
            return new Promise((resolve) => {
              window.__interactionQa.resolvePermission = () => resolve(stream);
            });
          },
        },
      });
    } else {
      Object.defineProperty(window, "MediaRecorder", { configurable: true, value: undefined });
      Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: undefined });
    }
  }, { supportVoice, storedMode, audioMode, permissionMode });

  await page.route("**/api/config", async (route) => {
    counts.config += 1;
    const body = {
      mode: options.contentMode || "coaching",
      ...(options.intakeSchema ? { intake_schema: true } : {}),
      ...(configVoice ? { voice: { enabled: true, stt: "fake", tts: "fake" } } : {}),
    };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.route("**/api/voice/transcribe", async (route) => {
    counts.transcribe += 1;
    requests.push({ kind: "transcribe" });
    if (options.delayTranscribe) {
      pendingTranscriptions.push(route);
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ text: "합성된 테스트 전사" }),
    });
  });
  await page.route("**/api/chat", async (route) => {
    counts.chat += 1;
    const payload = JSON.parse(route.request().postData() || "{}");
    requests.push({ kind: "chat", payload });
    if (options.delayChat) {
      pendingChats.push({ route, turn: counts.chat });
      return;
    }
    if (options.chatFailure) {
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error_code: "provider_unavailable" }) });
      return;
    }
    const turn = counts.chat;
    const intake = options.contextualReplies
      ? { filled: [], unfilled: [{ id: "support", label: "도움을 주는 사람", red_flag: false }] }
      : null;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(responseBody(turn, { intake })),
    });
  });
  await page.route("**/api/voice/synthesize", async (route) => {
    counts.synthesize += 1;
    requests.push({ kind: "synthesize" });
    if (options.ttsFailure) {
      await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error_code: "provider_unavailable" }) });
      return;
    }
    await route.fulfill({ status: 200, contentType: "audio/wav", body: Buffer.from("RIFF-test-audio") });
  });

  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.querySelectorAll(".message-row-assistant").length === 1, null, { timeout: 5000 });
  if (supportVoice && configVoice) {
    await page.waitForSelector("#interaction-mode-switch:not([hidden])", { timeout: 5000 });
  }

  async function releaseChat(index = 0) {
    const pending = pendingChats[index];
    assert.ok(pending, "pending chat route exists");
    await pending.route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(responseBody(pending.turn)),
    });
  }

  async function releaseTranscription(index = 0) {
    const route = pendingTranscriptions[index];
    assert.ok(route, "pending transcription route exists");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ text: "지연된 테스트 전사" }),
    });
  }

  return { context, page, pageErrors, requests, counts, releaseChat, releaseTranscription };
}

async function assertNoPageErrors(fixture) {
  assert.deepEqual(fixture.pageErrors, [], `page errors: ${fixture.pageErrors.join(" | ")}`);
}

async function selectMode(page, mode) {
  await page.locator(`#interaction-mode-${mode}`).check();
  await page.waitForFunction((expected) => sessionStorage.getItem("lmwiki_interaction_mode") === expected, mode);
}

async function waitForAssistant(page, expectedCount) {
  await page.waitForFunction((count) => document.querySelectorAll(".message-row-assistant").length >= count, expectedCount, { timeout: 7000 });
  await page.waitForSelector("#reset-session:not([disabled])", { timeout: 7000 });
}

async function recordToReview(page) {
  await page.locator("#voice-toggle").click();
  await page.waitForFunction(() => document.querySelector("#voice-toggle")?.getAttribute("aria-pressed") === "true", null, { timeout: 3000 });
  await sleep(850);
  await page.locator("#voice-toggle").click();
  await page.waitForSelector("#voice-review:not([hidden])", { timeout: 5000 });
  await page.waitForFunction(() => {
    const transcript = document.querySelector("#voice-transcript");
    const send = document.querySelector("#voice-send");
    return Boolean(transcript?.value && send && !send.disabled);
  }, null, { timeout: 5000 });
}

async function scenarioDefaultChat() {
  const fixture = await createFixture();
  try {
    assert.equal(await fixture.page.locator("#interaction-mode-chat").isChecked(), true);
    assert.equal(await fixture.page.locator("#chat-surface").isVisible(), true);
    assert.equal(await fixture.page.locator("#voice-surface").isHidden(), true);
    await fixture.page.locator("#message-input").fill("기본 채팅 검증");
    await fixture.page.locator("#send-button").click();
    await waitForAssistant(fixture.page, 2);
    const chat = fixture.requests.find((item) => item.kind === "chat");
    assert.deepEqual(Object.keys(chat.payload).sort(), ["message", "participant_id", "session_id", "session_token"]);
    assert.equal(fixture.counts.transcribe, 0);
    assert.equal(fixture.counts.synthesize, 0);
    pass("default-chat", { chat_calls: 1, voice_calls: 0, payload_fields: 4 });
    await assertNoPageErrors(fixture);
  } finally {
    await fixture.context.close();
  }
}

async function scenarioVoiceEntryRestore() {
  const fixture = await createFixture();
  try {
    await fixture.page.locator("#message-input").fill("보존할 채팅 초안");
    await selectMode(fixture.page, "voice");
    assert.equal(await fixture.page.locator("#interaction-mode-chat").isChecked(), false);
    assert.equal(await fixture.page.locator("#interaction-mode-voice").isChecked(), true);
    assert.equal(await fixture.page.locator("#chat-surface").isHidden(), true);
    assert.equal(await fixture.page.locator("#voice-surface").isVisible(), true);
    assert.equal(await fixture.page.locator("#message-input").inputValue(), "보존할 채팅 초안");
    assert.equal(await fixture.page.evaluate(() => document.activeElement?.id), "voice-toggle");
    await fixture.page.waitForFunction(() => {
      const chatLabel = document.querySelector("#interaction-mode-chat + .interaction-mode-label");
      const voiceLabel = document.querySelector("#interaction-mode-voice + .interaction-mode-label");
      return chatLabel && voiceLabel &&
        getComputedStyle(chatLabel).backgroundColor === "rgba(0, 0, 0, 0)" &&
        getComputedStyle(voiceLabel).backgroundColor !== "rgba(0, 0, 0, 0)";
    });
    await fixture.page.setViewportSize({ width: 1280, height: 800 });
    await fixture.page.screenshot({ path: SCREENSHOT_PATH });
    await fixture.page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await fixture.page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true);
    assert.equal(await fixture.page.locator("#voice-surface").isVisible(), true);
    pass("voice-entry", { stored_mode: "voice", one_active_surface: true });
    await assertNoPageErrors(fixture);
  } finally {
    await fixture.context.close();
  }

  const restored = await createFixture({ storedMode: "voice" });
  try {
    assert.equal(await restored.page.locator("#interaction-mode-voice").isChecked(), true);
    assert.equal(await restored.page.locator("#voice-surface").isVisible(), true);
    pass("stored-voice-restore");
    await assertNoPageErrors(restored);
  } finally {
    await restored.context.close();
  }
}

async function scenarioUnsupportedReload() {
  const fixture = await createFixture({ supportVoice: false, storedMode: "voice" });
  try {
    assert.equal(await fixture.page.locator("#interaction-mode-switch").isVisible(), true);
    assert.equal(await fixture.page.locator("#interaction-mode-switch").getAttribute("inert"), null);
    assert.equal(await fixture.page.locator("#interaction-mode-chat").isEnabled(), true);
    assert.equal(await fixture.page.locator("#interaction-mode-voice").isDisabled(), true);
    assert.equal(await fixture.page.locator("#chat-surface").isVisible(), true);
    assert.equal(await fixture.page.locator("#voice-surface").isHidden(), true);
    assert.equal(await fixture.page.evaluate(() => sessionStorage.getItem("lmwiki_interaction_mode")), "chat");
    pass("unsupported-reload", { forced_mode: "chat", selector_visible: true, voice_disabled: true });
    await assertNoPageErrors(fixture);
  } finally {
    await fixture.context.close();
  }
}

async function scenarioMalformedStorage() {
  const fixture = await createFixture({ storedMode: "not-a-mode" });
  try {
    assert.equal(await fixture.page.locator("#interaction-mode-chat").isChecked(), true);
    assert.equal(await fixture.page.locator("#interaction-mode-voice").isChecked(), false);
    assert.equal(await fixture.page.locator("#chat-surface").isVisible(), true);
    assert.equal(await fixture.page.evaluate(() => sessionStorage.getItem("lmwiki_interaction_mode")), "chat");
    pass("malformed-storage-fallback", { forced_mode: "chat" });
    await assertNoPageErrors(fixture);
  } finally {
    await fixture.context.close();
  }
}

async function scenarioContinuityAndReset() {
  const fixture = await createFixture();
  try {
    await fixture.page.locator("#message-input").fill("첫 번째 채팅");
    await fixture.page.locator("#send-button").click();
    await waitForAssistant(fixture.page, 2);
    const first = fixture.requests.find((item) => item.kind === "chat").payload;
    await fixture.page.locator("#message-input").fill("유지할 초안");
    await selectMode(fixture.page, "voice");
    await selectMode(fixture.page, "chat");
    assert.equal(await fixture.page.locator("#message-input").inputValue(), "유지할 초안");
    assert.equal(await fixture.page.locator(".message-row").count(), 3);
    assert.equal(await fixture.page.evaluate(() => sessionStorage.getItem("lmwiki_session_id")), first.session_id);
    await selectMode(fixture.page, "voice");
    await fixture.page.locator("#reset-session").click();
    assert.equal(await fixture.page.locator("#interaction-mode-voice").isChecked(), true);
    assert.equal(await fixture.page.locator("#voice-surface").isVisible(), true);
    assert.equal(await fixture.page.locator(".message-row").count(), 1);
    assert.equal(await fixture.page.locator("#turn-counter").textContent(), "0/10");
    assert.notEqual(await fixture.page.evaluate(() => sessionStorage.getItem("lmwiki_session_id")), first.session_id);
    pass("draft-history-session-continuity-and-reset", { mode_after_reset: "voice", turn_after_reset: 0 });
    await assertNoPageErrors(fixture);
  } finally {
    await fixture.context.close();
  }
}

async function scenarioSwitchDuringPermission() {
  const fixture = await createFixture({ permissionMode: "deferred" });
  try {
    await selectMode(fixture.page, "voice");
    await fixture.page.locator("#voice-toggle").click();
    await fixture.page.waitForFunction(() => window.lmwikiVoiceController?.getState() === "requesting_permission");
    await selectMode(fixture.page, "chat");
    await fixture.page.evaluate(() => window.__interactionQa.resolvePermission());
    await fixture.page.waitForFunction(() => window.__interactionQa.tracks[0]?.stopped === true);
    assert.equal(fixture.counts.transcribe, 0);
    assert.equal(fixture.counts.chat, 0);
    assert.equal(await fixture.page.locator("#voice-review").isHidden(), true);
    pass("switch-during-permission", { chat_calls: 0, transcribe_calls: 0, track_stopped: true });
    await assertNoPageErrors(fixture);
  } finally {
    await fixture.context.close();
  }
}

async function scenarioSwitchDuringRecording() {
  const fixture = await createFixture();
  try {
    await selectMode(fixture.page, "voice");
    await fixture.page.locator("#voice-toggle").click();
    await fixture.page.waitForFunction(() => window.lmwikiVoiceController?.getState() === "recording");
    await selectMode(fixture.page, "chat");
    await fixture.page.waitForFunction(() => window.__interactionQa.tracks[0]?.stopped === true);
    assert.equal(fixture.counts.transcribe, 0);
    assert.equal(fixture.counts.chat, 0);
    assert.equal(await fixture.page.locator("#voice-review").isHidden(), true);
    pass("switch-during-recording", { chat_calls: 0, transcribe_calls: 0, track_stopped: true });
    await assertNoPageErrors(fixture);
  } finally {
    await fixture.context.close();
  }
}

async function scenarioSwitchDuringTranscribe() {
  const fixture = await createFixture({ delayTranscribe: true });
  try {
    await selectMode(fixture.page, "voice");
    await fixture.page.locator("#voice-toggle").click();
    await fixture.page.waitForFunction(() => window.lmwikiVoiceController?.getState() === "recording");
    await sleep(850);
    await fixture.page.locator("#voice-toggle").click();
    await fixture.page.waitForFunction(() => window.lmwikiVoiceController?.getState() === "transcribing");
    await selectMode(fixture.page, "chat");
    await fixture.releaseTranscription();
    await sleep(50);
    assert.equal(await fixture.page.locator("#voice-review").isHidden(), true);
    assert.equal(fixture.counts.chat, 0);
    assert.equal(fixture.counts.synthesize, 0);
    pass("switch-during-transcribe", { chat_calls: 0, synthesize_calls: 0, stale_review_hidden: true });
    await assertNoPageErrors(fixture);
  } finally {
    await fixture.context.close();
  }
}

async function scenarioSwitchAfterConfirm() {
  const fixture = await createFixture({ delayChat: true });
  try {
    await selectMode(fixture.page, "voice");
    await recordToReview(fixture.page);
    assert.equal(fixture.counts.chat, 0);
    await fixture.page.locator("#voice-send").click();
    await fixture.page.waitForFunction(() => document.querySelectorAll(".message-row-user").length === 1);
    assert.equal(fixture.counts.chat, 1);
    await selectMode(fixture.page, "chat");
    await fixture.releaseChat();
    await waitForAssistant(fixture.page, 2);
    const chat = fixture.requests.find((item) => item.kind === "chat");
    assert.deepEqual(Object.keys(chat.payload).sort(), ["message", "participant_id", "session_id", "session_token"]);
    assert.equal(fixture.counts.synthesize, 0);
    assert.equal(await fixture.page.locator("#voice-review").isHidden(), true);
    assert.notEqual(await fixture.page.evaluate(() => document.activeElement?.id), "voice-toggle");
    pass("switch-after-confirm", { chat_calls: 1, synthesize_calls: 0, assistant_rendered: true });
    await assertNoPageErrors(fixture);
  } finally {
    await fixture.context.close();
  }
}

async function scenarioAutomaticTts() {
  const fixture = await createFixture();
  try {
    await selectMode(fixture.page, "voice");
    await recordToReview(fixture.page);
    assert.equal(fixture.counts.chat, 0);
    await fixture.page.locator("#voice-send").click();
    await waitForAssistant(fixture.page, 2);
    await fixture.page.waitForFunction(() => window.__interactionQa.audioPlayCalls === 1);
    assert.equal(fixture.counts.chat, 1);
    assert.equal(fixture.counts.synthesize, 1);
    assert.equal(await fixture.page.evaluate(() => window.__interactionQa.getUserMediaCalls), 1);
    assert.equal(await fixture.page.locator("#voice-surface").getAttribute("data-voice-state"), "ready");
    pass("auto-tts-allowed", { chat_calls: 1, synthesize_calls: 1, microphone_starts: 1 });
    await assertNoPageErrors(fixture);
  } finally {
    await fixture.context.close();
  }

  const failed = await createFixture({ ttsFailure: true });
  try {
    await selectMode(failed.page, "voice");
    await recordToReview(failed.page);
    await failed.page.locator("#voice-send").click();
    await waitForAssistant(failed.page, 2);
    await failed.page.waitForFunction(() => document.querySelector(".tts-status")?.textContent.includes("텍스트"));
    assert.equal(await failed.page.locator("#voice-surface").getAttribute("data-voice-state"), "ready");
    assert.equal(await failed.page.locator(".message-row-assistant").last().isVisible(), true);
    pass("auto-tts-failed", { synthesize_calls: 1, text_preserved: true, voice_state: "ready" });
    await assertNoPageErrors(failed);
  } finally {
    await failed.context.close();
  }
}

async function scenarioAutoplayBlocked() {
  const fixture = await createFixture({ audioMode: "blocked" });
  try {
    await selectMode(fixture.page, "voice");
    await recordToReview(fixture.page);
    await fixture.page.locator("#voice-send").click();
    await waitForAssistant(fixture.page, 2);
    await fixture.page.waitForFunction(() => document.querySelector(".tts-status")?.textContent.includes("자동 재생"));
    assert.equal(await fixture.page.locator("#voice-surface").getAttribute("data-voice-state"), "ready");
    assert.equal(fixture.counts.synthesize, 1);
    await fixture.page.locator(".tts-button").click();
    await fixture.page.waitForFunction(() => window.__interactionQa.audioPlayCalls === 2);
    assert.equal(fixture.counts.synthesize, 1);
    pass("autoplay-blocked", { synthesize_calls: 1, resume_calls: 1, text_preserved: true });
    await assertNoPageErrors(fixture);
  } finally {
    await fixture.context.close();
  }
}

async function scenarioQuickAndContextual() {
  const fixture = await createFixture({ contentMode: "intake", intakeSchema: true, contextualReplies: true });
  try {
    await selectMode(fixture.page, "voice");
    await fixture.page.locator("#chips .chip").first().click();
    await waitForAssistant(fixture.page, 2);
    await fixture.page.waitForFunction(() => window.__interactionQa.audioPlayCalls >= 1);
    await fixture.page.locator("#contextual-replies .reply-suggestion").first().click();
    await waitForAssistant(fixture.page, 3);
    await fixture.page.waitForFunction(() => window.__interactionQa.audioPlayCalls >= 2);
    const chats = fixture.requests.filter((item) => item.kind === "chat").map((item) => item.payload);
    assert.equal(chats.length, 2);
    assert.equal(chats[0].session_id, chats[1].session_id);
    assert.equal(chats[1].session_token, "session-token-1");
    assert.equal(await fixture.page.locator("#turn-counter").textContent(), "2/10");
    assert.equal(await fixture.page.evaluate(() => window.__interactionQa.getUserMediaCalls), 0);
    pass("voice-quick-and-contextual-reply", { chat_calls: 2, synthesize_calls: 2, turn: 2, microphone_starts: 0 });
    await assertNoPageErrors(fixture);
  } finally {
    await fixture.context.close();
  }
}

async function scenarioChatFailureReview() {
  const fixture = await createFixture({ chatFailure: true });
  try {
    await selectMode(fixture.page, "voice");
    await recordToReview(fixture.page);
    const before = await fixture.page.locator("#voice-transcript").inputValue();
    await fixture.page.locator("#voice-send").click();
    await fixture.page.waitForFunction(() => document.querySelector("#voice-review-status")?.textContent.includes("전송에 실패"));
    assert.equal(await fixture.page.locator("#voice-transcript").inputValue(), before);
    assert.equal(fixture.counts.chat, 1);
    assert.equal(fixture.counts.synthesize, 0);
    pass("chat-failure-preserves-current-epoch-review", { chat_calls: 1, synthesize_calls: 0 });
    await assertNoPageErrors(fixture);
  } finally {
    await fixture.context.close();
  }
}

const scenarios = {
  "switch-during-recording": scenarioSwitchDuringRecording,
  "switch-during-transcribe": scenarioSwitchDuringTranscribe,
  "switch-after-confirm": scenarioSwitchAfterConfirm,
  "autoplay-blocked": scenarioAutoplayBlocked,
  "unsupported-reload": scenarioUnsupportedReload,
};

try {
  if (requestedScenario === "all") {
    await scenarioDefaultChat();
    await scenarioVoiceEntryRestore();
    await scenarioUnsupportedReload();
    await scenarioMalformedStorage();
    await scenarioContinuityAndReset();
    await scenarioSwitchDuringPermission();
    await scenarioSwitchDuringRecording();
    await scenarioSwitchDuringTranscribe();
    await scenarioSwitchAfterConfirm();
    await scenarioAutomaticTts();
    await scenarioAutoplayBlocked();
    await scenarioQuickAndContextual();
    await scenarioChatFailureReview();
  } else {
    await scenarios[requestedScenario]();
  }
  console.log(JSON.stringify({
    task: "T6 chat-voice dual-mode integration",
    status: "pass",
    requested_scenario: requestedScenario,
    scenarios: results,
    screenshot: requestedScenario === "all" ? ".omo/evidence/task-6-chat-voice-dual-mode.png" : null,
  }));
} catch (error) {
  console.error(JSON.stringify({
    task: "T6 chat-voice dual-mode integration",
    status: "fail",
    requested_scenario: requestedScenario,
    passed_before_failure: results.map((item) => item.name),
    failure: error instanceof Error ? error.message : String(error),
  }));
  process.exitCode = 1;
} finally {
  await browser.close().catch(() => {});
  if (staticServer) await new Promise((resolve) => staticServer.close(resolve));
}
