import { chromium } from "playwright";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const BASE_URL = process.env.VOICE_E2E_BASE_URL;
const FIXTURE = path.resolve(
  process.env.VOICE_E2E_FIXTURE || path.join(ROOT, "tests/fixtures/voice-ko/01.wav"),
);
const SCREENSHOT = process.env.VOICE_E2E_SCREENSHOT
  ? path.resolve(process.env.VOICE_E2E_SCREENSHOT)
  : "";
const TIMEOUT_MS = Number.parseInt(process.env.VOICE_E2E_TIMEOUT_MS || "120000", 10);
const WAV_HEADER_BYTES = 44;

if (!BASE_URL || !/^http:\/\/127\.0\.0\.1:\d+$/.test(BASE_URL)) {
  throw new Error("VOICE_E2E_BASE_URL must be an explicit http://127.0.0.1:<port> URL");
}
if (!Number.isSafeInteger(TIMEOUT_MS) || TIMEOUT_MS < 5_000) {
  throw new Error("VOICE_E2E_TIMEOUT_MS must be an integer of at least 5000");
}

const endpointKind = (url) => {
  const pathname = new URL(url).pathname;
  if (pathname === "/api/voice/transcribe") return "stt";
  if (pathname === "/api/chat") return "chat";
  if (pathname === "/api/voice/synthesize") return "tts";
  return null;
};

const browser = await chromium.launch({
  headless: true,
  args: [
    "--autoplay-policy=no-user-gesture-required",
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    `--use-file-for-fake-audio-capture=${FIXTURE}`,
  ],
});

const context = await browser.newContext({ permissions: ["microphone"] });
const page = await context.newPage();
page.setDefaultTimeout(TIMEOUT_MS);

await page.addInitScript(() => {
  const probe = {
    playCallCount: 0,
    playFulfilledCount: 0,
    playRejectedCount: 0,
    playedObjectUrls: [],
    createdObjectUrls: [],
    revokedObjectUrls: [],
    activeObjectUrls: 0,
    audioBlobBytes: 0,
    audioBlobContentType: "",
    synthResponseBytes: 0,
    synthResponseContentType: "",
    synthResponseRiffHeaderValid: false,
    synthResponseWaveHeaderValid: false,
    ttsStates: [],
  };
  const trackedUrls = new Set();
  const nativeCreateObjectURL = URL.createObjectURL;
  const nativeRevokeObjectURL = URL.revokeObjectURL;
  const nativePlay = HTMLMediaElement.prototype.play;
  const nativeFetch = window.fetch.bind(window);

  window.fetch = async function (...args) {
    const response = await nativeFetch(...args);
    const input = args[0];
    const requestUrl = typeof input === "string" ? input : input?.url;
    const pathname = new URL(requestUrl || response.url, window.location.href).pathname;
    if (pathname === "/api/voice/synthesize") {
      const copy = response.clone();
      const bytes = new Uint8Array(await copy.arrayBuffer());
      probe.synthResponseBytes = bytes.byteLength;
      probe.synthResponseContentType = copy.headers.get("content-type") || "";
      probe.synthResponseRiffHeaderValid = bytes.byteLength >= 4
        && String.fromCharCode(...bytes.subarray(0, 4)) === "RIFF";
      probe.synthResponseWaveHeaderValid = bytes.byteLength >= 12
        && String.fromCharCode(...bytes.subarray(8, 12)) === "WAVE";
    }
    return response;
  };

  URL.createObjectURL = function (blob) {
    const value = nativeCreateObjectURL.call(URL, blob);
    probe.createdObjectUrls.push(value);
    trackedUrls.add(value);
    probe.activeObjectUrls = trackedUrls.size;
    if (blob && typeof blob.type === "string" && blob.type.startsWith("audio/")) {
      probe.audioBlobBytes = Number(blob.size) || 0;
      probe.audioBlobContentType = blob.type;
    }
    return value;
  };
  URL.revokeObjectURL = function (value) {
    nativeRevokeObjectURL.call(URL, value);
    probe.revokedObjectUrls.push(value);
    trackedUrls.delete(value);
    probe.activeObjectUrls = trackedUrls.size;
  };
  HTMLMediaElement.prototype.play = function (...args) {
    probe.playCallCount += 1;
    probe.playedObjectUrls.push(this.currentSrc || this.src);
    let result;
    try {
      result = nativePlay.apply(this, args);
    } catch (error) {
      probe.playRejectedCount += 1;
      throw error;
    }
    void Promise.resolve(result).then(
      () => {
        probe.playFulfilledCount += 1;
      },
      () => {
        probe.playRejectedCount += 1;
      },
    );
    return result;
  };

  let nativeCreateTtsPlayer;
  Object.defineProperty(window, "createTtsPlayer", {
    configurable: true,
    enumerable: true,
    get() {
      return nativeCreateTtsPlayer;
    },
    set(value) {
      nativeCreateTtsPlayer = function (options) {
        const originalOnStateChange = options?.onStateChange;
        const player = value({
          ...options,
          onStateChange(snapshot) {
            probe.ttsStates.push(snapshot.state);
            originalOnStateChange?.(snapshot);
          },
        });
        probe.ttsStates.push(player.getSnapshot().state);
        return player;
      };
    },
  });
  window.__voiceT7TtsProbe = probe;
});

const requests = [];
const responses = [];
const ttsResponses = [];
const pageErrors = [];
const externalRequests = [];
let canonicalChatPayload = false;
const confirmedMessage = "음성 모드 로컬 검증";

page.on("pageerror", (error) => pageErrors.push(error.message));
page.on("request", (request) => {
  const url = new URL(request.url());
  if (url.protocol === "http:" && url.hostname !== "127.0.0.1") {
    externalRequests.push(`${request.method()} ${url.origin}${url.pathname}`);
  }
  const kind = endpointKind(request.url());
  if (kind) {
    requests.push({ kind, method: request.method() });
    if (kind === "chat") {
      const payload = JSON.parse(request.postData() || "{}");
      canonicalChatPayload = payload.message === confirmedMessage
        && typeof payload.session_id === "string"
        && payload.session_id.length > 0
        && typeof payload.participant_id === "string"
        && payload.participant_id.length > 0
        && payload.session_token === null
        && !Object.hasOwn(payload, "interaction_mode")
        && Object.keys(payload).sort().join(",") === "message,participant_id,session_id,session_token";
    }
  }
});
page.on("response", (response) => {
  const kind = endpointKind(response.url());
  if (kind) {
    responses.push({ kind, status: response.status() });
    if (kind === "tts") {
      ttsResponses.push(response);
    }
  }
});

const countRequests = (kind) => requests.filter((request) => request.kind === kind).length;
const responseStatus = (kind) => responses.find((response) => response.kind === kind)?.status;

try {
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded" });

  const modeSelector = page.locator("#interaction-mode-switch");
  await modeSelector.waitFor({ state: "visible" });
  const voiceMode = page.locator("#interaction-mode-voice");
  if (!(await voiceMode.isEnabled())) throw new Error("Voice mode entry is disabled");
  if (!(await page.locator('label[for="interaction-mode-voice"]').innerText()).includes("음성")) {
    throw new Error("Voice mode entry label is missing");
  }

  await voiceMode.check();
  if (!(await voiceMode.isChecked())) throw new Error("Voice mode did not become active");
  if (!(await page.locator("#voice-surface").isVisible())) throw new Error("Voice surface is not visible");
  if (await page.locator("#chat-surface").isVisible()) throw new Error("Chat surface remained visible");

  await page.locator("#voice-toggle").click();
  await page.waitForFunction(() => {
    const button = document.querySelector("#voice-toggle");
    return button?.getAttribute("aria-pressed") === "true";
  });
  await page.waitForFunction(() => {
    const controller = window.lmwikiVoiceController;
    return controller?.getSnapshot().elapsedMs >= 850;
  });
  await page.locator("#voice-toggle").click();

  const review = page.locator("#voice-review");
  await review.waitFor({ state: "visible" });
  const transcript = page.locator("#voice-transcript");
  await page.waitForFunction(() => {
    const field = document.querySelector("#voice-transcript");
    const snapshot = window.lmwikiVoiceController?.getSnapshot();
    return (field && !field.disabled && field.value.trim().length > 0) || snapshot?.state === "error";
  });
  const voiceState = await page.evaluate(() => window.lmwikiVoiceController?.getSnapshot().state || "missing");
  if (!(await transcript.inputValue()).trim()) {
    throw new Error(`Real STT did not reach editable review: voice_state=${voiceState}`);
  }
  if (!(await transcript.isEditable())) throw new Error("Transcript review is not editable");
  if (countRequests("stt") !== 1 || countRequests("chat") !== 0 || countRequests("tts") !== 0) {
    throw new Error("Request ordering changed before transcript confirmation");
  }

  await transcript.fill(confirmedMessage);
  const assistantCountBefore = await page.locator(".message-row-assistant").count();
  await page.locator("#voice-send").click();
  await page.waitForFunction(
    (count) => document.querySelectorAll(".message-row-assistant").length > count,
    assistantCountBefore,
  );
  await page.waitForFunction(() => {
    const status = document.querySelector("#voice-status")?.textContent || "";
    const button = document.querySelector("#voice-toggle");
    return status.includes("새 음성 입력") && button && !button.disabled;
  });
  await page.waitForLoadState("networkidle");

  const happyCounts = {
    stt: countRequests("stt"),
    chat: countRequests("chat"),
    tts: countRequests("tts"),
  };
  if (happyCounts.stt !== 1 || happyCounts.chat !== 1 || happyCounts.tts !== 1) {
    throw new Error(`Expected one STT/chat/TTS request, got ${JSON.stringify(happyCounts)}`);
  }
  if (!canonicalChatPayload) throw new Error("Edited review did not reach the canonical chat payload");
  const happyOrder = requests.slice(0, 3).map((request) => request.kind);
  if (happyOrder.join(",") !== "stt,chat,tts") {
    throw new Error(`Unexpected request order: ${happyOrder.join(",")}`);
  }
  for (const kind of ["stt", "chat", "tts"]) {
    if (responseStatus(kind) !== 200) throw new Error(`${kind} returned HTTP ${responseStatus(kind)}`);
  }
  if (ttsResponses.length !== 1) {
    throw new Error(`Expected exactly one retained TTS Response, got ${ttsResponses.length}`);
  }
  const ttsResponseObject = ttsResponses[0];
  const ttsContentType = ttsResponseObject.headers()["content-type"] || "";

  const assistantTextPresent = Boolean(
    (await page.locator(".message-row-assistant").last().innerText()).trim(),
  );
  if (!assistantTextPresent) throw new Error("Assistant response text is empty");
  const finalState = await page.evaluate(() => ({
    voice: window.lmwikiVoiceController?.getSnapshot().state || "missing",
    tts: window.lmwikiTtsPlayer?.getSnapshot().state || "missing",
    mode: window.lmwikiInteractionModeController?.getSnapshot() || null,
  }));
  if (finalState.tts !== "idle") throw new Error(`TTS did not settle: tts=${finalState.tts}`);
  if (finalState.mode?.interactionMode !== "voice" || finalState.mode?.voicePhase !== "ready") {
    throw new Error("Interaction mode did not settle in Voice/ready");
  }
  const ttsPlayback = await page.evaluate(() => ({ ...window.__voiceT7TtsProbe }));
  const ttsResponse = {
    status: ttsResponseObject.status(),
    content_type: ttsContentType,
    browser_clone_content_type: ttsPlayback.synthResponseContentType,
    content_type_wav_compatible: /^audio\/(?:wav|wave|x-wav|vnd\.wave)(?:\s*;|$)/i.test(ttsContentType.trim())
      && /^audio\/(?:wav|wave|x-wav|vnd\.wave)(?:\s*;|$)/i.test(ttsPlayback.synthResponseContentType.trim()),
    byte_length: ttsPlayback.synthResponseBytes,
    body_nonempty_beyond_header: ttsPlayback.synthResponseBytes > WAV_HEADER_BYTES,
    riff_header_valid: ttsPlayback.synthResponseRiffHeaderValid,
    wave_header_valid: ttsPlayback.synthResponseWaveHeaderValid,
  };
  ttsResponse.wav_header_valid = ttsResponse.riff_header_valid && ttsResponse.wave_header_valid;
  if (ttsResponse.status !== 200
      || !ttsResponse.content_type_wav_compatible
      || !ttsResponse.body_nonempty_beyond_header
      || !ttsResponse.wav_header_valid) {
    throw new Error(`TTS response was not non-empty WAV audio: ${JSON.stringify(ttsResponse)}`);
  }
  if (ttsPlayback.playCallCount !== 1
      || ttsPlayback.playFulfilledCount !== 1
      || ttsPlayback.playRejectedCount !== 0) {
    throw new Error(`Native HTMLAudioElement.play proof failed: ${JSON.stringify(ttsPlayback)}`);
  }
  const createdTtsUrl = ttsPlayback.createdObjectUrls[0];
  const sameTtsObjectUrlRevokedOnce = ttsPlayback.createdObjectUrls.length === 1
    && ttsPlayback.revokedObjectUrls.length === 1
    && createdTtsUrl === ttsPlayback.revokedObjectUrls[0]
    && ttsPlayback.playedObjectUrls.length === 1
    && createdTtsUrl === ttsPlayback.playedObjectUrls[0];
  if (!sameTtsObjectUrlRevokedOnce || ttsPlayback.activeObjectUrls !== 0) {
    throw new Error(`TTS object URL lifecycle proof failed: ${JSON.stringify(ttsPlayback)}`);
  }
  if (ttsPlayback.audioBlobBytes !== ttsResponse.byte_length
      || !ttsPlayback.audioBlobContentType.toLowerCase().startsWith("audio/wav")) {
    throw new Error(`Browser audio Blob did not match synth response: ${JSON.stringify(ttsPlayback)}`);
  }
  const expectedTtsStates = ["idle", "synthesizing", "playing", "idle"];
  if (ttsPlayback.ttsStates.join(",") !== expectedTtsStates.join(",")) {
    throw new Error(`Unexpected TTS state transitions: ${ttsPlayback.ttsStates.join(",")}`);
  }

  const malformed = await page.evaluate(async () => {
    const body = new FormData();
    body.append("session_id", crypto.randomUUID());
    body.append("audio", new Blob([new Uint8Array([0, 1, 2, 3])], { type: "audio/webm" }), "malformed.webm");
    const response = await fetch("/api/voice/transcribe", { method: "POST", body });
    const payload = await response.json();
    return { status: response.status, error_code: payload.error_code || "missing_error_code" };
  });
  if (malformed.status !== 400 || malformed.error_code !== "invalid_audio") {
    throw new Error(`Malformed browser media was not classified: ${JSON.stringify(malformed)}`);
  }

  if (SCREENSHOT) await page.screenshot({ path: SCREENSHOT, fullPage: true });
  if (pageErrors.length) throw new Error(`Uncaught page errors: ${pageErrors.join(" | ")}`);
  if (externalRequests.length) throw new Error(`Non-loopback requests observed: ${externalRequests.join(" | ")}`);

  console.log(JSON.stringify({
    schema_version: 1,
    task: "T7 chat-voice-dual-mode browser real local",
    result: "pass",
    base_url: BASE_URL,
    browser: "chromium",
    media: {
      input: "synthetic WAV via Chromium fake microphone",
      recorder: "MediaRecorder",
      upload_container: "WebM",
      physical_microphone: "UNAVAILABLE",
    },
    assertions: {
      voice_mode_entry: true,
      transcript_review_editable: true,
      assistant_text_present: assistantTextPresent,
      ready: true,
      automatic_play_policy: "no-user-gesture-required",
      html_media_play_fulfilled_once: true,
      tts_object_url_same_revoke_once: sameTtsObjectUrlRevokedOnce,
      tts_response_valid: true,
      canonical_chat_payload: canonicalChatPayload,
      duplicate_requests: 0,
    },
    happy_path: {
      request_counts: happyCounts,
      request_order: happyOrder,
      response_statuses: { stt: 200, chat: 200, tts: 200 },
    },
    tts_response: ttsResponse,
    tts_playback: {
      play_call_count: ttsPlayback.playCallCount,
      play_fulfilled_count: ttsPlayback.playFulfilledCount,
      play_rejected_count: ttsPlayback.playRejectedCount,
      played_object_urls: ttsPlayback.playedObjectUrls,
      created_object_url_count: ttsPlayback.createdObjectUrls.length,
      created_object_urls: ttsPlayback.createdObjectUrls,
      revoked_object_url_count: ttsPlayback.revokedObjectUrls.length,
      revoked_object_urls: ttsPlayback.revokedObjectUrls,
      same_tts_object_url_revoked_once: sameTtsObjectUrlRevokedOnce,
      verified_at_tts_state: finalState.tts,
      final_active_object_urls: ttsPlayback.activeObjectUrls,
      audio_blob_bytes: ttsPlayback.audioBlobBytes,
      audio_blob_content_type: ttsPlayback.audioBlobContentType,
    },
    tts_state_transitions: ttsPlayback.ttsStates,
    malformed_browser_media: malformed,
    external_network_requests: 0,
    page_errors: 0,
    screenshot: SCREENSHOT ? path.relative(ROOT, SCREENSHOT) : null,
    redaction: { raw_audio: false, transcript: false, secrets: false },
  }));
} finally {
  await context.close().catch(() => {});
  await browser.close().catch(() => {});
}
