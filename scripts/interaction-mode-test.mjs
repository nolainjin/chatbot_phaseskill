import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const sourceUrl = new URL("../static/interaction-mode.js", import.meta.url);
const source = await readFile(sourceUrl, "utf8");

function loadFactory() {
  const sandbox = {};
  sandbox.globalThis = sandbox;
  vm.runInNewContext(source, sandbox, { filename: "static/interaction-mode.js" });
  assert.equal(typeof sandbox.createInteractionModeController, "function");
  return sandbox.createInteractionModeController;
}

const factory = loadFactory();
const publicApi = [
  "captureEpoch",
  "getSnapshot",
  "isCurrentEpoch",
  "resetVoiceTurn",
  "setCapability",
  "setVoicePhase",
  "switchMode",
];

const scenarios = {
  "chat-default": () => {
    const controller = factory();
    assert.deepEqual(Object.keys(controller).sort(), publicApi);
    assert.deepEqual(
      JSON.parse(JSON.stringify(controller.getSnapshot())),
      {
        interactionMode: "chat",
        interactionEpoch: 0,
        voiceCapability: false,
        voicePhase: "idle",
      },
    );
    assert.equal(controller.captureEpoch(), 0);
    assert.equal(controller.isCurrentEpoch(0), true);
    assert.equal(controller.isCurrentEpoch(1), false);
    return { cleanupCount: 0 };
  },

  "voice-without-capability": () => {
    const controller = factory();
    const snapshot = controller.switchMode("voice");
    assert.equal(snapshot.interactionMode, "chat");
    assert.equal(snapshot.interactionEpoch, 0);
    assert.equal(snapshot.voicePhase, "idle");
    return { cleanupCount: 0 };
  },

  "mode-round-trip": () => {
    let cleanupCount = 0;
    const controller = factory({ onVoiceExit: () => { cleanupCount += 1; } });
    controller.setCapability(true);
    assert.equal(controller.switchMode("voice").interactionEpoch, 1);
    assert.equal(controller.setVoicePhase("recording", 1), true);
    const snapshot = controller.switchMode("chat");
    assert.equal(snapshot.interactionMode, "chat");
    assert.equal(snapshot.interactionEpoch, 2);
    assert.equal(snapshot.voicePhase, "idle");
    assert.equal(cleanupCount, 1);
    return { cleanupCount };
  },

  "same-mode-idempotence": () => {
    let cleanupCount = 0;
    const controller = factory({ onVoiceExit: () => { cleanupCount += 1; } });
    assert.equal(controller.switchMode("chat").interactionEpoch, 0);
    controller.setCapability(true);
    controller.switchMode("voice");
    controller.setVoicePhase("review");
    const snapshot = controller.switchMode("voice");
    assert.equal(snapshot.interactionEpoch, 1);
    assert.equal(snapshot.voicePhase, "review");
    assert.equal(cleanupCount, 0);
    return { cleanupCount };
  },

  "stale-epoch": () => {
    let cleanupCount = 0;
    let staleCleanupUpdate;
    let voiceEpoch;
    let controller;
    controller = factory({
      onVoiceExit: () => {
        cleanupCount += 1;
        assert.equal(controller.isCurrentEpoch(voiceEpoch), false);
        staleCleanupUpdate = controller.setVoicePhase("speaking", voiceEpoch);
      },
    });
    controller.setCapability(true);
    controller.switchMode("voice");
    voiceEpoch = controller.captureEpoch();
    controller.setVoicePhase("transcribing", voiceEpoch);
    controller.switchMode("chat");
    assert.equal(staleCleanupUpdate, false);
    controller.switchMode("voice");
    assert.equal(controller.setVoicePhase("review", voiceEpoch), false);
    assert.equal(controller.resetVoiceTurn(voiceEpoch), false);
    assert.equal(controller.getSnapshot().voicePhase, "idle");
    assert.equal(cleanupCount, 1);
    return { cleanupCount };
  },

  "capability-loss": () => {
    let cleanupCount = 0;
    let cleanupSnapshot;
    const controller = factory({
      onVoiceExit: () => {
        cleanupCount += 1;
        cleanupSnapshot = controller.getSnapshot();
      },
    });
    controller.setCapability(true);
    controller.switchMode("voice");
    controller.setVoicePhase("recording");
    const voiceEpoch = controller.captureEpoch();
    const snapshot = controller.setCapability(false);
    assert.equal(controller.isCurrentEpoch(voiceEpoch), false);
    assert.deepEqual(JSON.parse(JSON.stringify(snapshot)), {
      interactionMode: "chat",
      interactionEpoch: 2,
      voiceCapability: false,
      voicePhase: "idle",
    });
    assert.deepEqual(
      JSON.parse(JSON.stringify(cleanupSnapshot)),
      JSON.parse(JSON.stringify(snapshot)),
    );
    assert.equal(cleanupCount, 1);
    controller.setCapability(false);
    assert.equal(controller.captureEpoch(), 2);
    assert.equal(cleanupCount, 1);
    return { cleanupCount };
  },

  "voice-turn-reset": () => {
    const controller = factory();
    controller.setCapability(true);
    controller.switchMode("voice");
    const epoch = controller.captureEpoch();
    controller.setVoicePhase("ready", epoch);
    assert.equal(controller.resetVoiceTurn(epoch), true);
    assert.equal(controller.getSnapshot().voicePhase, "idle");
    return { cleanupCount: 0 };
  },

  "allowed-phases": () => {
    const controller = factory();
    controller.setCapability(true);
    controller.switchMode("voice");
    const epoch = controller.captureEpoch();
    const phases = [
      "idle",
      "requesting_permission",
      "recording",
      "transcribing",
      "review",
      "sending",
      "synthesizing",
      "speaking",
      "ready",
      "error",
    ];
    for (const phase of phases) {
      assert.equal(controller.setVoicePhase(phase, epoch), true);
      assert.equal(controller.getSnapshot().voicePhase, phase);
    }
    return { cleanupCount: 0 };
  },

  "invalid-input": () => {
    const controller = factory();
    assert.throws(() => controller.switchMode("coaching"), /Invalid interaction mode/);
    for (const phase of ["starting", "stopping", "transcript_review"]) {
      assert.throws(() => controller.setVoicePhase(phase), /Invalid voice phase/);
    }
    assert.throws(() => controller.setCapability("yes"), /boolean/);
    return { cleanupCount: 0 };
  },
};

const scenarioFlag = process.argv.indexOf("--scenario");
const requestedScenario = scenarioFlag === -1 ? null : process.argv[scenarioFlag + 1];
if (scenarioFlag !== -1 && !requestedScenario) {
  throw new Error("--scenario requires a scenario name");
}
if (requestedScenario && !Object.hasOwn(scenarios, requestedScenario)) {
  throw new Error(`Unknown scenario: ${requestedScenario}`);
}

const selected = requestedScenario ? [requestedScenario] : Object.keys(scenarios);
const results = selected.map((name) => ({ name, result: "pass", ...scenarios[name]() }));

assert.doesNotMatch(source, /document\.|querySelector|sessionStorage|fetch\s*\(|\/api\/chat/i);
assert.doesNotMatch(source, /provider|SpeechRecognition|addEventListener|dispatchEvent/i);

console.log(JSON.stringify({
  task: "T1 interaction mode controller",
  scenario: requestedScenario || "all",
  result: "pass",
  cleanupCount: results.reduce((total, item) => total + item.cleanupCount, 0),
  scenarios: results,
}));
