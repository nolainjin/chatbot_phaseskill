import { strict as assert } from "node:assert";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const source = await readFile(new URL("../static/tts.js", import.meta.url), "utf8");
const sandbox = { AbortController, Blob };
sandbox.globalThis = sandbox;
vm.runInNewContext(source, sandbox, { filename: "static/tts.js" });
const createTtsPlayer = sandbox.createTtsPlayer;
assert.equal(typeof createTtsPlayer, "function");

const scenarioIndex = process.argv.indexOf("--scenario");
const requested = scenarioIndex === -1 ? "all" : process.argv[scenarioIndex + 1];

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, reject, resolve };
}

function namedError(name, message = name) {
  return Object.assign(new Error(message), { name });
}

function flush() {
  return new Promise((resolve) => setImmediate(resolve));
}

function fixture({ synthesize, play } = {}) {
  const synthCalls = [];
  const states = [];
  const created = [];
  const revoked = [];
  const instances = [];
  const URLApi = {
    createObjectURL(blob) {
      const value = `blob:tts-${created.length + 1}`;
      created.push({ blob, value });
      return value;
    },
    revokeObjectURL(value) {
      revoked.push(value);
    },
  };
  class FakeAudio {
    constructor(src) {
      this.src = src;
      this.playCalls = 0;
      this.pauseCalls = 0;
      this.clearCalls = 0;
      this.onended = null;
      this.onerror = null;
      instances.push(this);
    }
    play() {
      this.playCalls += 1;
      return play ? play(this, this.playCalls) : Promise.resolve();
    }
    pause() {
      this.pauseCalls += 1;
    }
    removeAttribute(name) {
      if (name === "src") {
        this.clearCalls += 1;
        this.src = "";
      }
    }
    emitEnded() {
      this.onended?.();
    }
    emitError() {
      this.onerror?.({ type: "error" });
    }
  }
  const voiceApi = {
    synthesize(text, metadata, requestOptions) {
      const call = { metadata, requestOptions, text };
      synthCalls.push(call);
      return synthesize
        ? synthesize(call, synthCalls.length)
        : Promise.resolve(new Blob(["audio"]));
    },
  };
  const player = createTtsPlayer({
    AbortController,
    Audio: FakeAudio,
    URL: URLApi,
    onStateChange: (snapshot) => states.push(snapshot),
    voiceApi,
  });
  return { created, instances, player, revoked, states, synthCalls };
}

const scenarios = {
  async "automatic-play"() {
    const f = fixture();
    const result = await f.player.play("자동 음성", { automatic: true, epoch: 4 });
    assert.equal(result.classification, "played");
    assert.equal(f.player.getState(), "playing");
    assert.equal(f.instances[0].playCalls, 1);
    assert.equal(f.player.getSnapshot().automatic, true);
    assert.equal(f.player.getSnapshot().epoch, 4);
    f.instances[0].emitEnded();
    assert.equal(f.player.getState(), "idle");
    assert.deepEqual(f.revoked, ["blob:tts-1"]);
  },

  async "autoplay-blocked"() {
    const f = fixture({
      play: (_audio, count) => count === 1
        ? Promise.reject(namedError("NotAllowedError"))
        : Promise.resolve(),
    });
    const blocked = await f.player.play("재생 허용", { automatic: true, epoch: 7 });
    const audio = f.instances[0];
    assert.equal(blocked.classification, "blocked");
    assert.equal(f.player.getState(), "blocked");
    assert.equal(f.player.getSnapshot().canResume, true);
    assert.equal(f.revoked.length, 0);
    const originalUrl = audio.src;
    const resumed = await f.player.resume();
    assert.equal(resumed.classification, "played");
    assert.equal(f.instances.length, 1);
    assert.equal(audio.src, originalUrl);
    assert.equal(audio.playCalls, 2);
    assert.equal((await f.player.resume()).classification, "failed");
    assert.equal(audio.playCalls, 2);
    audio.emitEnded();
    assert.deepEqual(f.revoked, [originalUrl]);
  },

  async "synth-503"() {
    const error = Object.assign(namedError("VoiceApiError"), { code: "provider_unavailable", status: 503 });
    const f = fixture({ synthesize: async () => { throw error; } });
    const result = await f.player.play("실패");
    assert.equal(result.classification, "failed");
    assert.equal(f.player.getState(), "error");
    assert.equal(f.player.getSnapshot().error.status, 503);
    assert.equal(f.created.length, 0);
    assert.equal(f.instances.length, 0);
  },

  async "audio-error"() {
    const rejected = fixture({ play: () => Promise.reject(namedError("NotSupportedError")) });
    assert.equal((await rejected.player.play("지원 실패")).classification, "failed");
    assert.equal(rejected.player.getState(), "error");
    assert.deepEqual(rejected.revoked, ["blob:tts-1"]);
    const emitted = fixture();
    assert.equal((await emitted.player.play("재생 중 실패")).classification, "played");
    emitted.instances[0].emitError();
    assert.equal(emitted.player.getState(), "error");
    assert.deepEqual(emitted.revoked, ["blob:tts-1"]);
  },

  async "stop-during-synth"() {
    const pending = deferred();
    const f = fixture({ synthesize: (call) => {
      call.requestOptions.signal.addEventListener("abort", () => pending.reject(namedError("AbortError")), { once: true });
      return pending.promise;
    } });
    const resultPromise = f.player.play("준비 중 중지", { epoch: 1 });
    assert.equal(f.player.getState(), "synthesizing");
    assert.equal(f.player.stop(), true);
    assert.equal((await resultPromise).classification, "aborted");
    assert.equal(f.player.getState(), "idle");
    assert.equal(f.player.stop(), false);
    assert.equal(f.created.length, 0);
  },

  async "stop-during-playback"() {
    const f = fixture();
    await f.player.play("재생 중 중지");
    const audio = f.instances[0];
    assert.equal(f.player.stop(), true);
    assert.equal(audio.pauseCalls, 1);
    assert.equal(audio.clearCalls, 1);
    assert.deepEqual(f.revoked, ["blob:tts-1"]);
    assert.equal(f.player.stop(), false);
    assert.equal(audio.pauseCalls, 1);
  },

  async "stale-playback"() {
    const first = deferred();
    let firstAudio = null;
    const f = fixture({ play: (audio) => {
      if (!firstAudio) {
        firstAudio = audio;
        return first.promise;
      }
      return Promise.resolve();
    } });
    const oldResult = f.player.play("오래된 응답", { epoch: 1 });
    await flush();
    assert.equal(f.instances.length, 1);
    const newResult = await f.player.play("새 응답", { epoch: 2 });
    first.resolve();
    assert.equal((await oldResult).classification, "aborted");
    assert.equal(newResult.classification, "played");
    assert.equal(firstAudio.pauseCalls, 1);
    assert.equal(firstAudio.onended, null);
    assert.deepEqual(f.revoked, ["blob:tts-1"]);
    assert.equal(f.player.getSnapshot().epoch, 2);
    f.instances[1].emitEnded();
    assert.deepEqual(f.revoked, ["blob:tts-1", "blob:tts-2"]);
  },

  async "text-cap"() {
    const f = fixture();
    const result = await f.player.play("가".repeat(1201));
    assert.equal(f.synthCalls[0].text.length, 1200);
    assert.equal(result.truncated, true);
    assert.equal(result.truncation.visible, true);
    assert.equal(result.truncation.omittedChars, 1);
    assert.equal(f.player.getSnapshot().truncation.sentChars, 1200);
    f.instances[0].emitEnded();
  },

  async "url-revocation"() {
    const f = fixture();
    await f.player.play("첫 응답");
    const firstAudio = f.instances[0];
    await f.player.play("둘째 응답");
    assert.equal(firstAudio.pauseCalls, 1);
    assert.deepEqual(f.revoked, ["blob:tts-1"]);
    f.instances[1].emitEnded();
    assert.deepEqual(f.revoked, ["blob:tts-1", "blob:tts-2"]);
    assert.equal(new Set(f.revoked).size, f.revoked.length);
  },

  async "malformed-input"() {
    const f = fixture();
    assert.equal((await f.player.play("   ")).classification, "failed");
    assert.equal(f.synthCalls.length, 0);
    assert.equal(f.created.length, 0);
  },

  async "source-contract"() {
    const f = fixture();
    assert.deepEqual(Array.from(f.player.STATES), ["idle", "synthesizing", "playing", "blocked", "error"]);
    assert.equal(f.player.getSnapshot().state, "idle");
    const browser = { AbortController, Blob };
    browser.window = browser;
    vm.runInNewContext(source, browser, { filename: "static/tts.js" });
    assert.equal(typeof browser.createTtsPlayer, "function");
    assert.doesNotMatch(source, /\bdocument\b|querySelector|innerHTML|removeChild/);
    assert.doesNotMatch(source, /\bfetch\s*\(|FileReader|data:audio|setInterval/);
  },
};

assert.ok(requested === "all" || Object.hasOwn(scenarios, requested), `unknown scenario: ${requested}`);
const selected = requested === "all" ? Object.entries(scenarios) : [[requested, scenarios[requested]]];
const results = [];
for (const [name, run] of selected) {
  await run();
  results.push({ name, result: "pass" });
}
console.log(JSON.stringify({ result: "pass", scenarios: results }));
