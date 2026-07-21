(function (root) {
  "use strict";

  var INTERACTION_MODES = ["chat", "voice"];
  var VOICE_PHASES = [
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

  function createInteractionModeController(options) {
    options = options || {};
    if (options.onVoiceExit !== undefined && typeof options.onVoiceExit !== "function") {
      throw new TypeError("onVoiceExit must be a function");
    }

    var onVoiceExit = options.onVoiceExit || function () {};
    var interactionMode = "chat";
    var interactionEpoch = 0;
    var voiceCapability = false;
    var voicePhase = "idle";

    function getSnapshot() {
      return Object.freeze({
        interactionMode: interactionMode,
        interactionEpoch: interactionEpoch,
        voiceCapability: voiceCapability,
        voicePhase: voicePhase,
      });
    }

    function captureEpoch() {
      return interactionEpoch;
    }

    function isCurrentEpoch(epoch) {
      return epoch === interactionEpoch;
    }

    function assertMode(mode) {
      if (INTERACTION_MODES.indexOf(mode) === -1) {
        throw new TypeError("Invalid interaction mode: " + String(mode));
      }
    }

    function assertVoicePhase(phase) {
      if (VOICE_PHASES.indexOf(phase) === -1) {
        throw new TypeError("Invalid voice phase: " + String(phase));
      }
    }

    function switchMode(mode) {
      assertMode(mode);
      var nextMode = mode === "voice" && !voiceCapability ? "chat" : mode;
      if (nextMode === interactionMode) return getSnapshot();

      var leavingVoice = interactionMode === "voice";
      interactionEpoch += 1;
      interactionMode = nextMode;
      voicePhase = "idle";

      if (leavingVoice) onVoiceExit();
      return getSnapshot();
    }

    function setCapability(capability) {
      if (typeof capability !== "boolean") {
        throw new TypeError("Voice capability must be a boolean");
      }
      if (voiceCapability === capability) return getSnapshot();

      voiceCapability = capability;
      if (!voiceCapability) return switchMode("chat");
      return getSnapshot();
    }

    function setVoicePhase(phase, epoch) {
      assertVoicePhase(phase);
      var expectedEpoch = epoch === undefined ? interactionEpoch : epoch;
      if (!isCurrentEpoch(expectedEpoch)) return false;
      if (interactionMode !== "voice" && phase !== "idle") return false;

      voicePhase = phase;
      return true;
    }

    function resetVoiceTurn(epoch) {
      return setVoicePhase("idle", epoch);
    }

    return Object.freeze({
      getSnapshot: getSnapshot,
      setCapability: setCapability,
      switchMode: switchMode,
      setVoicePhase: setVoicePhase,
      captureEpoch: captureEpoch,
      isCurrentEpoch: isCurrentEpoch,
      resetVoiceTurn: resetVoiceTurn,
    });
  }

  root.createInteractionModeController = createInteractionModeController;
})(typeof globalThis !== "undefined" ? globalThis : this);
