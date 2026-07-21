import { readFile } from "node:fs/promises";
import { strict as assert } from "node:assert";
import { performance } from "node:perf_hooks";
import vm from "node:vm";

const source = await readFile(new URL("../static/voice.js", import.meta.url), "utf8");
const scenarioIndex = process.argv.indexOf("--scenario");
const requestedScenario = scenarioIndex === -1 ? "all" : process.argv[scenarioIndex + 1];
assert.ok(["all", "hostile-events"].includes(requestedScenario), `unknown scenario: ${requestedScenario}`);

class FakeTrack {
  constructor() {
    this.stopped = false;
    this.listeners = new Map();
  }

  addEventListener(name, handler) {
    this.listeners.set(name, handler);
  }

  emit(name) {
    const handler = this.listeners.get(name);
    if (handler) handler();
  }

  stop() {
    this.stopped = true;
  }
}

class FakeStream {
  constructor() {
    this.track = new FakeTrack();
    this.listeners = new Map();
  }

  getTracks() {
    return [this.track];
  }

  addEventListener(name, handler) {
    this.listeners.set(name, handler);
  }

  emit(name) {
    const handler = this.listeners.get(name);
    if (handler) handler();
  }
}

class FakeRecorder {
  static instances = [];
  static isTypeSupported(mime) {
    return mime === "audio/webm;codecs=opus";
  }

  constructor(stream, options = {}) {
    this.stream = stream;
    this.mimeType = options.mimeType || "audio/webm";
    this.state = "inactive";
    this.stopCalls = 0;
    this.onstart = null;
    this.onstop = null;
    this.ondataavailable = null;
    this.onerror = null;
    FakeRecorder.instances.push(this);
  }

  start() {
    this.state = "recording";
    this.onstart?.();
  }

  stop() {
    this.stopCalls += 1;
    this.state = "inactive";
  }

  emitData(size) {
    const data = size > 0 ? new Uint8Array(size) : new Uint8Array(0);
    this.ondataavailable?.({ data });
  }

  emitMetadata(size = 32) {
    this.ondataavailable?.({ data: { size, metadata: true } });
  }

  emitStop() {
    this.onstop?.();
  }

  emitError() {
    this.onerror?.(new Error("fake recorder error"));
  }
}

class FakeDocument {
  constructor() {
    this.visibilityState = "visible";
    this.listeners = new Map();
  }

  addEventListener(name, handler) {
    this.listeners.set(name, handler);
  }

  emit(name) {
    this.listeners.get(name)?.();
  }
}

function loadFactory() {
  const sandbox = {
    AbortController,
    Blob,
    clearInterval,
    clearTimeout,
    performance,
    setInterval,
    setTimeout,
  };
  sandbox.globalThis = sandbox;
  vm.runInNewContext(source, sandbox, { filename: "static/voice.js" });
  return sandbox.createVoiceController;
}

function loadVoiceApi() {
  const sandbox = {
    AbortController,
    Blob,
    FormData,
    clearTimeout,
    fetch: null,
    setTimeout,
  };
  sandbox.globalThis = sandbox;
  vm.runInNewContext(source, sandbox, { filename: "static/voice.js" });
  return sandbox.createVoiceApi;
}

function createFixture({ transcribe, document, getUserMedia, stream: suppliedStream, onTranscriptReady } = {}) {
  let clock = 0;
  const stream = suppliedStream || new FakeStream();
  const events = [];
  const states = [];
  const transcriptions = [];
  const factory = loadFactory();
  const controller = factory({
    AbortController,
    Blob,
    MediaRecorder: FakeRecorder,
    mediaDevices: { getUserMedia: getUserMedia || (async () => stream) },
    document,
    enabled: true,
    minRecordingMs: 800,
    maxRecordingMs: 60000,
    minAudioBytes: 256,
    clickDebounceMs: 0,
    now: () => clock,
    onStateChange: (snapshot) => states.push(snapshot.state),
    onRecordingReady: (blob) => {
      events.push("recording-ready");
      transcriptions.push(blob);
    },
    onTranscriptReady,
    transcribe: transcribe || (async () => {
      events.push("transcribe");
      return { text: "테스트 전사" };
    }),
  });
  return {
    controller,
    stream,
    events,
    states,
    transcriptions,
    clock: { advance: (ms) => { clock += ms; } },
    recorder: () => FakeRecorder.instances.at(-1),
  };
}

async function begin(fixture) {
  FakeRecorder.instances.length = 0;
  await fixture.controller.start();
  assert.equal(fixture.controller.getState(), "recording");
  return fixture.recorder();
}

async function flush() {
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
}

async function runScenario(name, fn) {
  await fn();
  return { name, result: "pass" };
}

const results = [];

results.push(await runScenario("error-before-data", async () => {
  const fixture = createFixture();
  const recorder = await begin(fixture);
  fixture.clock.advance(900);
  recorder.emitError();
  recorder.emitData(512);
  recorder.emitStop();
  await flush();
  assert.equal(fixture.controller.getState(), "error");
  assert.equal(fixture.transcriptions.length, 0);
  assert.equal(fixture.stream.track.stopped, true);
}));

results.push(await runScenario("permission-denied-and-no-device", async () => {
  const denied = createFixture({
    getUserMedia: async () => { throw Object.assign(new Error("denied"), { name: "NotAllowedError" }); },
  });
  await denied.controller.start();
  assert.equal(denied.controller.getState(), "error");

  const noTracks = { getTracks: () => [] };
  const missing = createFixture({ getUserMedia: async () => noTracks });
  await missing.controller.start();
  assert.equal(missing.controller.getState(), "error");
}));

results.push(await runScenario("starting-stop-race", async () => {
  FakeRecorder.instances.length = 0;
  let resolvePermission;
  const permission = new Promise((resolve) => { resolvePermission = resolve; });
  const lateStream = new FakeStream();
  const fixture = createFixture({
    getUserMedia: () => permission,
    stream: lateStream,
  });
  const starting = fixture.controller.start();
  await flush();
  assert.equal(fixture.controller.getState(), "requesting_permission");
  assert.equal(fixture.controller.stop(), false);
  fixture.controller.reset();
  resolvePermission(lateStream);
  assert.equal(await starting, false);
  assert.equal(fixture.controller.getState(), "idle");
  assert.equal(lateStream.track.stopped, true);
  assert.equal(FakeRecorder.instances.length, 0);
  assert.deepEqual(fixture.events, []);
}));

results.push(await runScenario("data-before-stop", async () => {
  const fixture = createFixture({
    transcribe: async () => {
      fixture.events.push("transcribe");
      return { text: "final" };
    },
  });
  const recorder = await begin(fixture);
  fixture.clock.advance(900);
  assert.equal(fixture.controller.stop(), true);
  recorder.emitData(64);
  fixture.events.push("final-chunk");
  recorder.emitData(512);
  recorder.emitStop();
  await flush();
  assert.deepEqual(fixture.events, ["final-chunk", "recording-ready", "transcribe"]);
  assert.equal(fixture.controller.getState(), "transcript_review");
  assert.equal(fixture.transcriptions[0].size, 576);
}));

results.push(await runScenario("track-ended-during-recording", async () => {
  const fixture = createFixture();
  const recorder = await begin(fixture);
  fixture.stream.track.emit("ended");
  recorder.emitData(512);
  recorder.emitStop();
  await flush();
  assert.equal(fixture.controller.getState(), "error");
  assert.equal(fixture.stream.track.stopped, true);
  assert.equal(fixture.transcriptions.length, 0);
}));

results.push(await runScenario("reset-during-transcribe", async () => {
  let resolveTranscribe;
  let transcriptCallbacks = 0;
  const fixture = createFixture({
    transcribe: () => new Promise((resolve) => { resolveTranscribe = resolve; }),
    onTranscriptReady: () => { transcriptCallbacks += 1; },
  });
  const recorder = await begin(fixture);
  fixture.clock.advance(900);
  fixture.controller.stop();
  recorder.emitData(512);
  recorder.emitStop();
  await flush();
  assert.equal(fixture.controller.getState(), "transcribing");
  fixture.controller.reset();
  resolveTranscribe({ text: "late" });
  await flush();
  assert.equal(fixture.controller.getState(), "idle");
  assert.equal(transcriptCallbacks, 0);
  assert.equal(fixture.stream.track.stopped, true);
}));

results.push(await runScenario("stop-twice", async () => {
  const fixture = createFixture();
  const recorder = await begin(fixture);
  fixture.clock.advance(900);
  assert.equal(fixture.controller.stop(), true);
  assert.equal(fixture.controller.stop(), false);
  assert.equal(recorder.stopCalls, 1);
  recorder.emitData(512);
  recorder.emitStop();
  await flush();
  assert.equal(fixture.events.filter((event) => event === "transcribe").length, 1);
}));

results.push(await runScenario("early-stop-and-empty-audio", async () => {
  const early = createFixture();
  const earlyRecorder = await begin(early);
  early.clock.advance(799);
  assert.equal(early.controller.stop(), false);
  assert.equal(earlyRecorder.stopCalls, 0);
  early.clock.advance(1);
  assert.equal(early.controller.stop(), true);
  earlyRecorder.emitData(512);
  earlyRecorder.emitStop();
  await flush();

  const empty = createFixture();
  const emptyRecorder = await begin(empty);
  empty.clock.advance(900);
  empty.controller.stop();
  emptyRecorder.emitData(0);
  emptyRecorder.emitMetadata();
  emptyRecorder.emitStop();
  await flush();
  assert.equal(empty.controller.getState(), "error");
  assert.equal(empty.transcriptions.length, 0);
}));

results.push(await runScenario("pagehide-stops-tracks", async () => {
  const document = new FakeDocument();
  const fixture = createFixture({ document });
  await begin(fixture);
  document.emit("pagehide");
  assert.equal(fixture.controller.getState(), "idle");
  assert.equal(fixture.stream.track.stopped, true);
}));

results.push(await runScenario("voice-fetch-wrapper-upload-and-errors", async () => {
  const calls = [];
  const api = loadVoiceApi()({
    fetch: async (url, options) => {
      calls.push({ url, options });
      return new Response(JSON.stringify({ text: "브라우저 전사", duration_ms: 1000 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    },
  });
  const result = await api.transcribe(new Blob([new Uint8Array(512)], { type: "audio/webm" }), {
    sessionId: "voice-browser",
    sessionToken: "token",
    participantId: "participant",
  });
  assert.equal(result.text, "브라우저 전사");
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "/api/voice/transcribe");
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.body.get("session_id"), "voice-browser");
  assert.equal(calls[0].options.body.get("audio").type, "audio/webm");

  const failingApi = loadVoiceApi()({
    fetch: async () => new Response(JSON.stringify({ error_code: "audio_too_large" }), {
      status: 413,
      headers: { "Content-Type": "application/json" },
    }),
  });
  await assert.rejects(
    failingApi.transcribe(new Blob([new Uint8Array(512)], { type: "audio/webm" }), {
      sessionId: "voice-browser",
    }),
    (error) => error.code === "audio_too_large" && error.message.includes("10 MiB"),
  );
}));

results.push(await runScenario("voice-fetch-wrapper-timeout-and-cancel", async () => {
  let timeoutSignal;
  const api = loadVoiceApi()({
    timeoutMs: 5,
    fetch: (_url, options) => new Promise((_resolve, reject) => {
      timeoutSignal = options.signal;
      options.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
    }),
  });
  await assert.rejects(
    api.synthesize("시간 초과"),
    (error) => error.code === "provider_timeout" && error.message.includes("시간이 초과"),
  );
  assert.equal(timeoutSignal.aborted, true);

  const cancelController = new AbortController();
  const cancelApi = loadVoiceApi()({
    fetch: (_url, options) => new Promise((_resolve, reject) => {
      options.signal.addEventListener("abort", () => reject(Object.assign(new Error("aborted"), { name: "AbortError" })));
    }),
  });
  const pending = cancelApi.synthesize("취소", { signal: cancelController.signal });
  cancelController.abort();
  await assert.rejects(pending, (error) => error.code === "request_cancelled");
}));

const html = await readFile(new URL("../static/index.html", import.meta.url), "utf8");
const app = await readFile(new URL("../static/app.js", import.meta.url), "utf8");
assert.match(html, /<button type="button" id="voice-toggle"/);
assert.match(html, /id="voice-status"[^>]+aria-live="polite"/);
assert.match(html, /id="voice-review"[^>]+hidden/);
assert.match(html, /<button type="button" id="voice-send"/);
assert.match(html, /<script src="voice\.js\?v=1"><\/script>/);
assert.doesNotMatch(source, /\/api\/chat/);
assert.doesNotMatch(source, /SpeechRecognition/);
assert.doesNotMatch(source, /pointerdown|pointerup|silence/i);
assert.match(app, /requestPending/);
assert.match(app, /voiceController\.setEnabled\(true\)/);

console.log(JSON.stringify({
  scenario: requestedScenario,
  scenarios: results,
  stateMachine: loadFactory()({
    AbortController,
    Blob,
    MediaRecorder: FakeRecorder,
    mediaDevices: { getUserMedia: async () => new FakeStream() },
    enabled: true,
  }).STATES,
  assertions: [
    "800ms early stop does not call stop",
    "duplicate stop calls recorder.stop once",
    "final dataavailable precedes transcribe seam",
    "empty and metadata-only audio rejected",
    "reset invalidates late transcribe callbacks",
    "permission resolution after reset stops the late stream without creating a recorder",
    "pagehide stops microphone tracks",
    "voice controller never calls /api/chat",
    "accessible button/status/review controls present",
  ],
}));
