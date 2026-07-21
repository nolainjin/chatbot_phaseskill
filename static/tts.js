(function (root) {
  "use strict";

  var STATES = ["idle", "synthesizing", "playing", "blocked", "error"];
  var MAX_TTS_CHARS = 1200;

  function normalizeError(error) {
    return {
      name: error && error.name ? String(error.name) : "Error",
      code: error && error.code ? String(error.code) : "",
      status: error && Number.isFinite(error.status) ? error.status : 0,
      message: error && error.message ? String(error.message) : "",
    };
  }

  function createError(name, code, message) {
    var error = new Error(message);
    error.name = name;
    error.code = code;
    return error;
  }

  function createTtsPlayer(options) {
    options = options || {};
    var voiceApi = options.voiceApi;
    var AudioCtor = options.Audio || root.Audio;
    var URLApi = options.URL || root.URL;
    var AbortCtor = options.AbortController || root.AbortController;
    var onStateChange = options.onStateChange;
    var getMetadata = typeof options.getMetadata === "function"
      ? options.getMetadata
      : function () { return options.metadata || {}; };

    if (!voiceApi || typeof voiceApi.synthesize !== "function") {
      throw new Error("createTtsPlayer requires voiceApi.synthesize");
    }
    if (!AudioCtor || !URLApi || !AbortCtor) {
      throw new Error("createTtsPlayer requires Audio, URL, and AbortController");
    }

    var state = "idle";
    var serial = 0;
    var active = null;
    var context = null;
    var lastError = null;

    function copyTruncation(value) {
      if (!value) return null;
      return {
        visible: value.visible,
        maxChars: value.maxChars,
        originalChars: value.originalChars,
        sentChars: value.sentChars,
        omittedChars: value.omittedChars,
      };
    }

    function contextFor(attempt) {
      return {
        epoch: attempt.epoch,
        automatic: attempt.automatic,
        truncation: copyTruncation(attempt.truncation),
      };
    }

    function getSnapshot() {
      return {
        state: state,
        epoch: context ? context.epoch : null,
        automatic: context ? context.automatic : false,
        canResume: Boolean(active && state === "blocked" && active.canResume),
        truncated: Boolean(context && context.truncation),
        truncation: context ? copyTruncation(context.truncation) : null,
        error: lastError ? Object.assign({}, lastError) : null,
      };
    }

    function transition(nextState) {
      if (STATES.indexOf(nextState) === -1) throw new Error("Unknown TTS state: " + nextState);
      state = nextState;
      if (typeof onStateChange === "function") onStateChange(getSnapshot());
    }

    function isCurrent(attempt) {
      return active === attempt && attempt.id === serial;
    }

    function outcome(classification, attempt, error) {
      var truncation = attempt ? copyTruncation(attempt.truncation) : null;
      return {
        classification: classification,
        epoch: attempt ? attempt.epoch : null,
        automatic: attempt ? attempt.automatic : false,
        truncated: Boolean(truncation),
        truncation: truncation,
        error: error ? normalizeError(error) : null,
      };
    }

    function clearMedia(attempt, pauseAudio) {
      if (!attempt) return;
      var audio = attempt.audio;
      attempt.audio = null;
      if (audio) {
        audio.onended = null;
        audio.onerror = null;
        if (pauseAudio && typeof audio.pause === "function") {
          try { audio.pause(); } catch (error) {}
        }
        try {
          if (typeof audio.removeAttribute === "function") audio.removeAttribute("src");
          else audio.src = "";
        } catch (error) {}
      }
      if (attempt.objectUrl) {
        var objectUrl = attempt.objectUrl;
        attempt.objectUrl = "";
        if (typeof URLApi.revokeObjectURL === "function") {
          try { URLApi.revokeObjectURL(objectUrl); } catch (error) {}
        }
      }
    }

    function release(attempt, settings) {
      settings = settings || {};
      if (!attempt) return;
      if (settings.abort && attempt.controller && !attempt.controller.signal.aborted) {
        attempt.controller.abort();
      }
      clearMedia(attempt, settings.pause !== false);
      if (active === attempt) active = null;
    }

    function fail(attempt, error) {
      if (!isCurrent(attempt)) return outcome("aborted", attempt);
      context = contextFor(attempt);
      lastError = normalizeError(error);
      release(attempt, { pause: true });
      transition("error");
      return outcome("failed", attempt, error);
    }

    function stop() {
      var hadWork = Boolean(active || state !== "idle");
      serial += 1;
      var attempt = active;
      active = null;
      if (attempt) release(attempt, { abort: true, pause: true });
      context = null;
      lastError = null;
      if (state !== "idle") transition("idle");
      return hadWork;
    }

    async function startPlayback(attempt, isResume) {
      try {
        await Promise.resolve(attempt.audio.play());
      } catch (error) {
        if (!isCurrent(attempt)) return outcome("aborted", attempt);
        if (!isResume && error && error.name === "NotAllowedError") {
          attempt.canResume = true;
          context = contextFor(attempt);
          lastError = normalizeError(error);
          transition("blocked");
          return outcome("blocked", attempt, error);
        }
        return fail(attempt, error);
      }
      if (!isCurrent(attempt)) return outcome("aborted", attempt);
      attempt.canResume = false;
      lastError = null;
      transition("playing");
      return outcome("played", attempt);
    }

    async function play(text, playOptions) {
      playOptions = playOptions || {};
      stop();
      var originalText = String(text == null ? "" : text);
      var spokenText = originalText.slice(0, MAX_TTS_CHARS);
      var truncation = originalText.length > MAX_TTS_CHARS ? {
        visible: true,
        maxChars: MAX_TTS_CHARS,
        originalChars: originalText.length,
        sentChars: spokenText.length,
        omittedChars: originalText.length - spokenText.length,
      } : null;
      var attempt = {
        id: ++serial,
        epoch: Object.prototype.hasOwnProperty.call(playOptions, "epoch") ? playOptions.epoch : null,
        automatic: playOptions.automatic === true,
        truncation: truncation,
        controller: new AbortCtor(),
        audio: null,
        objectUrl: "",
        canResume: false,
      };
      context = contextFor(attempt);
      lastError = null;
      if (!spokenText.trim()) {
        var inputError = createError("TtsInputError", "invalid_text", "TTS text is empty");
        lastError = normalizeError(inputError);
        transition("error");
        return outcome("failed", attempt, inputError);
      }
      active = attempt;
      transition("synthesizing");
      var blob;
      try {
        blob = await voiceApi.synthesize(spokenText, getMetadata(attempt), { signal: attempt.controller.signal });
      } catch (error) {
        if (!isCurrent(attempt)) return outcome("aborted", attempt);
        if (error && error.name === "AbortError") {
          release(attempt, { pause: true });
          context = null;
          lastError = null;
          transition("idle");
          return outcome("aborted", attempt);
        }
        return fail(attempt, error);
      }
      if (!isCurrent(attempt)) return outcome("aborted", attempt);
      if (!blob || !Number.isFinite(blob.size) || blob.size <= 0) {
        return fail(attempt, createError("TtsAudioError", "invalid_audio", "TTS audio is empty"));
      }
      try {
        attempt.objectUrl = URLApi.createObjectURL(blob);
        attempt.audio = new AudioCtor(attempt.objectUrl);
      } catch (error) {
        return fail(attempt, error);
      }
      attempt.audio.onended = function () {
        if (!isCurrent(attempt)) return;
        release(attempt, { pause: false });
        context = null;
        lastError = null;
        transition("idle");
      };
      attempt.audio.onerror = function () {
        if (!isCurrent(attempt)) return;
        fail(attempt, createError("TtsAudioError", "playback_failed", "TTS audio playback failed"));
      };
      return startPlayback(attempt, false);
    }

    function resume() {
      var attempt = active;
      if (!attempt || state !== "blocked" || !attempt.canResume) {
        return Promise.resolve(outcome("failed", attempt));
      }
      attempt.canResume = false;
      return startPlayback(attempt, true);
    }

    return {
      STATES: STATES.slice(),
      getState: function () { return state; },
      getSnapshot: getSnapshot,
      play: play,
      resume: resume,
      stop: stop,
    };
  }

  root.createTtsPlayer = createTtsPlayer;
  root.TTS_PLAYER_STATES = STATES.slice();
})(typeof window !== "undefined" ? window : globalThis);
