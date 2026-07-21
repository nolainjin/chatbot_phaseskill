(function (root) {
  "use strict";

  var STATES = [
    "idle",
    "requesting_permission",
    "starting",
    "recording",
    "stopping",
    "transcribing",
    "transcript_review",
    "sending",
    "ready",
    "error",
  ];
  var DEFAULT_MIN_RECORDING_MS = 800;
  var DEFAULT_MAX_RECORDING_MS = 60 * 1000;
  var DEFAULT_MIN_AUDIO_BYTES = 256;
  var DEFAULT_CLICK_DEBOUNCE_MS = 220;

  function listen(target, eventName, handler) {
    if (!target) return;
    if (typeof target.addEventListener === "function") {
      target.addEventListener(eventName, handler);
    } else {
      target["on" + eventName] = handler;
    }
  }

  function stopTracks(stream) {
    if (!stream || typeof stream.getTracks !== "function") return;
    stream.getTracks().forEach(function (track) {
      if (track && typeof track.stop === "function") track.stop();
    });
  }

  function supportedMimeType(Recorder) {
    if (!Recorder) return "";
    var candidates = ["audio/webm;codecs=opus", "audio/mp4", ""];
    for (var i = 0; i < candidates.length; i += 1) {
      var mime = candidates[i];
      if (!mime || typeof Recorder.isTypeSupported !== "function") {
        if (!mime) return "";
        continue;
      }
      try {
        if (Recorder.isTypeSupported(mime)) return mime;
      } catch (error) {
      }
    }
    return "";
  }

  function createVoiceController(options) {
    options = options || {};
    var mediaDevices = options.mediaDevices || (root.navigator && root.navigator.mediaDevices);
    var Recorder = options.MediaRecorder || root.MediaRecorder;
    var BlobCtor = options.Blob || root.Blob;
    var AbortCtor = options.AbortController || root.AbortController;
    var now = options.now || function () {
      return root.performance && typeof root.performance.now === "function"
        ? root.performance.now()
        : Date.now();
    };
    var setTimeoutFn = options.setTimeout || root.setTimeout;
    var clearTimeoutFn = options.clearTimeout || root.clearTimeout;
    var setIntervalFn = options.setInterval || root.setInterval;
    var clearIntervalFn = options.clearInterval || root.clearInterval;
    var minRecordingMs = Number.isFinite(options.minRecordingMs)
      ? options.minRecordingMs
      : DEFAULT_MIN_RECORDING_MS;
    var maxRecordingMs = Number.isFinite(options.maxRecordingMs)
      ? options.maxRecordingMs
      : DEFAULT_MAX_RECORDING_MS;
    var minAudioBytes = Number.isFinite(options.minAudioBytes)
      ? options.minAudioBytes
      : DEFAULT_MIN_AUDIO_BYTES;
    var clickDebounceMs = Number.isFinite(options.clickDebounceMs)
      ? options.clickDebounceMs
      : DEFAULT_CLICK_DEBOUNCE_MS;

    var state = "idle";
    var enabled = options.enabled !== false;
    var attemptSerial = 0;
    var activeAttempt = null;
    var lastActionAt = -Infinity;
    var statusMessage = "";

    function emit() {
      if (typeof options.onStateChange !== "function") return;
      options.onStateChange({
        state: state,
        status: statusMessage,
        enabled: enabled,
        attemptId: activeAttempt ? activeAttempt.id : null,
        elapsedMs: activeAttempt ? activeAttempt.elapsedMs : 0,
        minRecordingMs: minRecordingMs,
        maxRecordingMs: maxRecordingMs,
      });
    }

    function transition(nextState, message) {
      if (STATES.indexOf(nextState) === -1) throw new Error("Unknown voice state: " + nextState);
      state = nextState;
      statusMessage = message || "";
      emit();
    }

    function isCurrent(attempt) {
      return activeAttempt === attempt && attempt.id === attemptSerial && !attempt.controller.signal.aborted;
    }

    function clearTimers(attempt) {
      if (!attempt) return;
      if (attempt.timerId !== null) clearIntervalFn(attempt.timerId);
      if (attempt.safetyTimerId !== null) clearTimeoutFn(attempt.safetyTimerId);
      attempt.timerId = null;
      attempt.safetyTimerId = null;
    }

    function cleanupAttempt(attempt) {
      if (!attempt || attempt.cleaned) return;
      attempt.cleaned = true;
      clearTimers(attempt);
      stopTracks(attempt.stream);
      attempt.stream = null;
      attempt.recorder = null;
    }

    function abortAttempt(attempt) {
      if (!attempt) return;
      if (!attempt.controller.signal.aborted) attempt.controller.abort();
      clearTimers(attempt);
      if (attempt.recorder && attempt.recorder.state === "recording") {
        try {
          attempt.recorder.stop();
        } catch (error) {}
      }
      cleanupAttempt(attempt);
    }

    function finishError(attempt, message) {
      if (!isCurrent(attempt)) return;
      activeAttempt = null;
      attemptSerial += 1;
      if (!attempt.controller.signal.aborted) attempt.controller.abort();
      cleanupAttempt(attempt);
      transition("error", message);
    }

    function updateElapsed(attempt) {
      if (!isCurrent(attempt) || attempt.startedAt === null) return;
      attempt.elapsedMs = Math.max(0, now() - attempt.startedAt);
      emit();
    }

    function beginTimer(attempt) {
      attempt.startedAt = now();
      attempt.elapsedMs = 0;
      attempt.timerId = setIntervalFn(function () {
        updateElapsed(attempt);
      }, 50);
      attempt.safetyTimerId = setTimeoutFn(function () {
        if (isCurrent(attempt) && state === "recording") stop({ force: true });
      }, maxRecordingMs);
    }

    function handleData(attempt, event) {
      if (!isCurrent(attempt) || !event || !event.data) return;
      var data = event.data;
      if (typeof data.size === "number" && data.size <= 0) return;
      attempt.chunks.push(data);
    }

    function completeRecording(attempt) {
      if (!isCurrent(attempt) || attempt.finalized) return;
      attempt.finalized = true;
      clearTimers(attempt);
      var blob;
      try {
        blob = new BlobCtor(attempt.chunks, { type: attempt.mimeType || "audio/webm" });
      } catch (error) {
        finishError(attempt, "녹음 파일을 준비하지 못했습니다. 다시 시도해 주세요.");
        return;
      }

      if (!blob || typeof blob.size !== "number" || blob.size < minAudioBytes) {
        finishError(attempt, "녹음 내용이 너무 짧습니다. 조금 더 말씀한 뒤 다시 시도해 주세요.");
        return;
      }

      transition("transcribing", "전사를 준비하고 있어요…");
      if (typeof options.onRecordingReady === "function") {
        options.onRecordingReady(blob, { attemptId: attempt.id, signal: attempt.controller.signal });
      }

      var transcribe = options.transcribe;
      if (typeof transcribe !== "function") {
        if (isCurrent(attempt)) {
          activeAttempt = null;
          attemptSerial += 1;
          cleanupAttempt(attempt);
          transition("transcript_review", "전사 확인을 기다리고 있습니다.");
        }
        return;
      }

      Promise.resolve()
        .then(function () {
          if (!isCurrent(attempt)) return null;
          return transcribe(blob, { attemptId: attempt.id, signal: attempt.controller.signal });
        })
        .then(function (result) {
          if (!isCurrent(attempt)) return;
          if (typeof options.onTranscriptReady === "function") options.onTranscriptReady(result, attempt.id);
          activeAttempt = null;
          attemptSerial += 1;
          cleanupAttempt(attempt);
          transition("transcript_review", "전사 내용을 확인해 주세요.");
        })
        .catch(function (error) {
          if (!isCurrent(attempt)) return;
          finishError(attempt, error && error.name === "AbortError" ? "전사가 취소되었습니다." : "전사에 실패했습니다. 다시 시도해 주세요.");
        });
    }

    function handleRecorderError(attempt) {
      finishError(attempt, "녹음 중 오류가 발생했습니다. 다시 시도해 주세요.");
    }

    function handleTrackEnded(attempt) {
      if (!isCurrent(attempt)) return;
      finishError(attempt, "마이크 연결이 끊겼습니다. 다시 시도해 주세요.");
    }

    function attachRecorder(attempt) {
      var mimeType = supportedMimeType(Recorder);
      attempt.mimeType = mimeType;
      try {
        attempt.recorder = mimeType ? new Recorder(attempt.stream, { mimeType: mimeType }) : new Recorder(attempt.stream);
      } catch (error) {
        finishError(attempt, "이 브라우저에서는 녹음을 시작할 수 없습니다.");
        return false;
      }
      attempt.recorder.ondataavailable = function (event) {
        handleData(attempt, event);
      };
      attempt.recorder.onerror = function () {
        handleRecorderError(attempt);
      };
      attempt.recorder.onstop = function () {
        completeRecording(attempt);
      };
      attempt.recorder.onstart = function () {
        if (!isCurrent(attempt) || state !== "starting") return;
        transition("recording", "녹음 중입니다. 말씀을 마친 뒤 녹음 종료를 눌러 주세요.");
        beginTimer(attempt);
      };
      try {
        attempt.recorder.start();
      } catch (error) {
        finishError(attempt, "녹음을 시작하지 못했습니다. 다시 시도해 주세요.");
        return false;
      }
      return true;
    }

    async function start() {
      var currentTime = now();
      if (!enabled || !mediaDevices || typeof mediaDevices.getUserMedia !== "function" || !Recorder) return false;
      if (["requesting_permission", "starting", "recording", "stopping", "transcribing", "sending"].indexOf(state) !== -1) return false;
      if (currentTime - lastActionAt < clickDebounceMs) return false;
      lastActionAt = currentTime;

      if (activeAttempt) abortAttempt(activeAttempt);
      var attempt = {
        id: ++attemptSerial,
        controller: new AbortCtor(),
        stream: null,
        recorder: null,
        chunks: [],
        mimeType: "",
        startedAt: null,
        elapsedMs: 0,
        timerId: null,
        safetyTimerId: null,
        stopRequested: false,
        finalized: false,
        cleaned: false,
      };
      activeAttempt = attempt;
      transition("requesting_permission", "마이크 권한을 요청하고 있습니다…");

      var stream;
      try {
        stream = await mediaDevices.getUserMedia({ audio: true });
      } catch (error) {
        if (isCurrent(attempt)) finishError(attempt, error && (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") ? "마이크 권한이 필요합니다." : "마이크를 사용할 수 없습니다. 장치를 확인해 주세요.");
        return false;
      }
      if (!isCurrent(attempt)) {
        stopTracks(stream);
        return false;
      }
      attempt.stream = stream;
      var tracks = typeof stream.getTracks === "function" ? stream.getTracks() : [];
      if (!tracks.length) {
        finishError(attempt, "사용할 수 있는 마이크 장치가 없습니다.");
        return false;
      }
      tracks.forEach(function (track) {
        listen(track, "ended", function () {
          handleTrackEnded(attempt);
        });
      });
      listen(stream, "inactive", function () {
        handleTrackEnded(attempt);
      });
      if (!isCurrent(attempt)) return false;
      transition("starting", "녹음 준비 중입니다…");
      attachRecorder(attempt);
      return true;
    }

    function stop(config) {
      config = config || {};
      if (!activeAttempt || state !== "recording" || activeAttempt.stopRequested) return false;
      var attempt = activeAttempt;
      var currentTime = now();
      if (!config.force && currentTime - lastActionAt < clickDebounceMs) return false;
      lastActionAt = currentTime;
      updateElapsed(attempt);
      if (!config.force && attempt.elapsedMs < minRecordingMs) {
        statusMessage = "조금 더 말씀하신 뒤 종료해 주세요.";
        emit();
        return false;
      }
      attempt.stopRequested = true;
      transition("stopping", "녹음 마무리 중입니다…");
      if (!attempt.recorder || attempt.recorder.state !== "recording") {
        finishError(attempt, "녹음을 마무리하지 못했습니다. 다시 시도해 주세요.");
        return false;
      }
      try {
        attempt.recorder.stop();
      } catch (error) {
        finishError(attempt, "녹음을 마무리하지 못했습니다. 다시 시도해 주세요.");
        return false;
      }
      return true;
    }

    function reset() {
      if (activeAttempt) {
        var attempt = activeAttempt;
        activeAttempt = null;
        attemptSerial += 1;
        abortAttempt(attempt);
      } else {
        attemptSerial += 1;
      }
      transition("idle", "");
    }

    function pageLifecycle() {
      reset();
    }

    function setEnabled(nextEnabled) {
      enabled = nextEnabled === true;
      if (!enabled && activeAttempt) reset();
      emit();
    }

    function isSupported() {
      return Boolean(mediaDevices && typeof mediaDevices.getUserMedia === "function" && Recorder && BlobCtor && AbortCtor);
    }

    if (options.document) {
      listen(options.document, "visibilitychange", function () {
        if (options.document.visibilityState === "hidden") pageLifecycle();
      });
      listen(options.document, "pagehide", pageLifecycle);
      listen(options.document, "beforeunload", pageLifecycle);
    }

    return {
      STATES: STATES.slice(),
      getState: function () {
        return state;
      },
      getSnapshot: function () {
        return {
          state: state,
          status: statusMessage,
          enabled: enabled,
          attemptId: activeAttempt ? activeAttempt.id : null,
          elapsedMs: activeAttempt ? activeAttempt.elapsedMs : 0,
        };
      },
      isSupported: isSupported,
      start: start,
      stop: stop,
      toggle: function () {
        return state === "recording" ? stop() : start();
      },
      reset: reset,
      pageLifecycle: pageLifecycle,
      setEnabled: setEnabled,
    };
  }

  root.createVoiceController = createVoiceController;
  root.VOICE_RECORDING_STATES = STATES.slice();
})(typeof window !== "undefined" ? window : globalThis);
