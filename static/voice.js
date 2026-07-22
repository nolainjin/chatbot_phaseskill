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
  var DEFAULT_SILENCE_THRESHOLD = 0.035;
  var DEFAULT_SILENCE_AFTER_MS = 1600;
  var DEFAULT_SILENCE_GRACE_MS = 1200;
  var DEFAULT_METER_INTERVAL_MS = 80;

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

  var VOICE_ERROR_MESSAGES = {
    voice_disabled: "음성 기능이 꺼져 있습니다. 텍스트 입력을 이용해 주세요.",
    invalid_request: "음성 요청을 확인해 주세요.",
    invalid_audio: "녹음 파일을 읽지 못했습니다. 다시 녹음해 주세요.",
    audio_too_large: "녹음 파일이 10 MiB보다 큽니다. 짧게 다시 녹음해 주세요.",
    audio_too_short: "조금 더 말씀하신 뒤 다시 녹음해 주세요.",
    audio_too_long: "녹음이 너무 깁니다. 60초 안으로 다시 녹음해 주세요.",
    provider_unavailable: "로컬 음성 기능을 사용할 수 없습니다. 텍스트 입력을 이용해 주세요.",
    provider_timeout: "로컬 음성 처리 시간이 초과되었습니다. 다시 시도해 주세요.",
    local_only_violation: "로컬 음성 연결을 확인하지 못했습니다. 다시 시도해 주세요.",
    session_auth_required: "세션 인증이 필요합니다. 새로고침 후 다시 시도해 주세요.",
    invalid_text: "읽을 텍스트를 확인해 주세요.",
  };

  function createVoiceError(code, status, detail) {
    var error = new Error(VOICE_ERROR_MESSAGES[code] || detail || "음성 요청에 실패했습니다. 다시 시도해 주세요.");
    error.name = code === "request_cancelled" ? "AbortError" : "VoiceApiError";
    error.code = code;
    error.status = status || 0;
    error.detail = detail || "";
    return error;
  }

  function createVoiceApi(options) {
    options = options || {};
    var fetchImpl = options.fetch || root.fetch;
    var FormDataCtor = options.FormData || root.FormData;
    var AbortCtor = options.AbortController || root.AbortController;
    var setTimeoutFn = options.setTimeout || root.setTimeout;
    var clearTimeoutFn = options.clearTimeout || root.clearTimeout;
    var defaultTimeoutMs = Number.isFinite(options.timeoutMs) ? options.timeoutMs : 45000;
    function addVoiceRequestHeader(requestOptions) {
      var next = Object.assign({}, requestOptions || {});
      var headers = next.headers || {};
      if (typeof Headers !== "undefined" && headers instanceof Headers) {
        headers = new Headers(headers);
        headers.set("X-Lmwiki-Voice-Request", "1");
      } else {
        headers = Object.assign({}, headers, { "X-Lmwiki-Voice-Request": "1" });
      }
      next.headers = headers;
      return next;
    }


    function request(path, requestOptions, timeoutMs) {
      if (typeof fetchImpl !== "function" || !FormDataCtor || !AbortCtor) {
        return Promise.reject(createVoiceError("provider_unavailable", 503, "브라우저 음성 API를 사용할 수 없습니다."));
      }
      requestOptions = addVoiceRequestHeader(requestOptions);
      var externalSignal = requestOptions.signal;
      return new Promise(function (resolve, reject) {
        var controller = new AbortCtor();
        var timedOut = false;
        var settled = false;
        var timeoutId = null;
        var onExternalAbort = null;

        function cleanup() {
          if (timeoutId !== null) clearTimeoutFn(timeoutId);
          if (externalSignal && onExternalAbort) externalSignal.removeEventListener("abort", onExternalAbort);
        }

        function fail(error) {
          if (settled) return;
          settled = true;
          cleanup();
          reject(error);
        }

        if (externalSignal) {
          onExternalAbort = function () {
            controller.abort();
            fail(createVoiceError("request_cancelled", 0, "요청이 취소되었습니다."));
          };
          if (externalSignal.aborted) {
            fail(createVoiceError("request_cancelled", 0, "요청이 취소되었습니다."));
            return;
          }
          externalSignal.addEventListener("abort", onExternalAbort, { once: true });
        }
        timeoutId = setTimeoutFn(function () {
          timedOut = true;
          controller.abort();
        }, Number.isFinite(timeoutMs) ? timeoutMs : defaultTimeoutMs);

        Promise.resolve(fetchImpl(path, Object.assign({}, requestOptions, { signal: controller.signal })))
          .then(async function (response) {
            if (response.ok) return response;
            var body = {};
            try {
              body = await response.json();
            } catch (error) {
              body = {};
            }
            var code = body && typeof body.error_code === "string" ? body.error_code : "provider_unavailable";
            throw createVoiceError(code, response.status, body && body.detail);
          })
          .then(function (response) {
            if (settled) return;
            settled = true;
            cleanup();
            resolve(response);
          })
          .catch(function (error) {
            if (error && error.name === "VoiceApiError") {
              fail(error);
              return;
            }
            if (timedOut) {
              fail(createVoiceError("provider_timeout", 504, "음성 요청 시간이 초과되었습니다."));
              return;
            }
            if (externalSignal && externalSignal.aborted) {
              fail(createVoiceError("request_cancelled", 0, "요청이 취소되었습니다."));
              return;
            }
            fail(createVoiceError("provider_unavailable", 503, "음성 요청에 연결하지 못했습니다."));
          });
      });
    }

    function transcribe(blob, metadata, requestOptions) {
      metadata = metadata || {};
      if (metadata.signal && !requestOptions) {
        requestOptions = metadata;
        metadata = {};
      }
      var form = new FormDataCtor();
      form.append("session_id", String(metadata.sessionId || ""));
      if (metadata.sessionToken) form.append("session_token", String(metadata.sessionToken));
      if (metadata.participantId) form.append("participant_id", String(metadata.participantId));
      if (Number.isFinite(metadata.durationMs)) form.append("duration_ms", String(metadata.durationMs));
      form.append("audio", blob, metadata.filename || "recording.webm");
      return request(
        "/api/voice/transcribe",
        Object.assign({ method: "POST", body: form }, requestOptions || {}),
        options.transcribeTimeoutMs || defaultTimeoutMs,
      )
        .then(function (response) { return response.json(); });
    }

    function synthesize(text, metadata, requestOptions) {
      metadata = metadata || {};
      if (metadata.signal && !requestOptions) {
        requestOptions = metadata;
        metadata = {};
      }
      return request(
        "/api/voice/synthesize",
        Object.assign({
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: String(text || ""),
            session_id: metadata.sessionId,
            session_token: metadata.sessionToken,
          }),
        }, requestOptions || {}),
        options.synthesizeTimeoutMs || defaultTimeoutMs,
      ).then(function (response) { return response.blob(); });
    }

    return {
      transcribe: transcribe,
      synthesize: synthesize,
      mapError: function (code) {
        return VOICE_ERROR_MESSAGES[code] || "음성 요청에 실패했습니다. 다시 시도해 주세요.";
      },
    };
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
    var AudioContextCtor = options.AudioContext || root.AudioContext || root.webkitAudioContext;
    var silenceAutoStop = options.silenceAutoStop === true;
    var silenceThreshold = Number.isFinite(options.silenceThreshold)
      ? options.silenceThreshold
      : DEFAULT_SILENCE_THRESHOLD;
    var silenceAfterMs = Number.isFinite(options.silenceAfterMs)
      ? options.silenceAfterMs
      : DEFAULT_SILENCE_AFTER_MS;
    var silenceGraceMs = Number.isFinite(options.silenceGraceMs)
      ? options.silenceGraceMs
      : DEFAULT_SILENCE_GRACE_MS;
    var meterIntervalMs = Number.isFinite(options.meterIntervalMs)
      ? options.meterIntervalMs
      : DEFAULT_METER_INTERVAL_MS;

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
        level: activeAttempt ? activeAttempt.level : 0,
        silenceMs: activeAttempt ? activeAttempt.silenceMs : 0,
        silenceAutoStop: silenceAutoStop,
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
      if (attempt.meterTimerId !== null) clearIntervalFn(attempt.meterTimerId);
      attempt.meterTimerId = null;
    }

    function cleanupAudioMeter(attempt) {
      if (!attempt) return;
      if (attempt.sourceNode && typeof attempt.sourceNode.disconnect === "function") {
        try {
          attempt.sourceNode.disconnect();
        } catch (error) {}
      }
      if (attempt.audioContext && typeof attempt.audioContext.close === "function") {
        try {
          var closed = attempt.audioContext.close();
          if (closed && typeof closed.catch === "function") closed.catch(function () {});
        } catch (error) {}
      }
      attempt.audioContext = null;
      attempt.analyser = null;
      attempt.audioBuffer = null;
      attempt.sourceNode = null;
    }

    function cleanupAttempt(attempt) {
      if (!attempt || attempt.cleaned) return;
      attempt.cleaned = true;
      clearTimers(attempt);
      cleanupAudioMeter(attempt);
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

    function readAudioLevel(attempt) {
      if (!attempt || !attempt.analyser || !attempt.audioBuffer) return 0;
      try {
        attempt.analyser.getByteTimeDomainData(attempt.audioBuffer);
      } catch (error) {
        return 0;
      }
      var sum = 0;
      for (var index = 0; index < attempt.audioBuffer.length; index += 1) {
        var sample = (attempt.audioBuffer[index] - 128) / 128;
        sum += sample * sample;
      }
      return Math.min(1, Math.sqrt(sum / attempt.audioBuffer.length) * 2.4);
    }

    function beginAudioMeter(attempt) {
      attempt.level = 0;
      attempt.silenceMs = 0;
      attempt.lastAudibleAt = now();
      if (!AudioContextCtor || !attempt.stream) return;
      try {
        attempt.audioContext = new AudioContextCtor();
        attempt.analyser = attempt.audioContext.createAnalyser();
        attempt.analyser.fftSize = 256;
        attempt.analyser.smoothingTimeConstant = 0.65;
        attempt.audioBuffer = new Uint8Array(attempt.analyser.fftSize);
        attempt.sourceNode = attempt.audioContext.createMediaStreamSource(attempt.stream);
        attempt.sourceNode.connect(attempt.analyser);
        if (attempt.audioContext.state === "suspended" && typeof attempt.audioContext.resume === "function") {
          var resumed = attempt.audioContext.resume();
          if (resumed && typeof resumed.catch === "function") resumed.catch(function () {});
        }
      } catch (error) {
        cleanupAudioMeter(attempt);
        return;
      }
      attempt.meterTimerId = setIntervalFn(function () {
        if (!isCurrent(attempt) || state !== "recording") return;
        var currentTime = now();
        var level = readAudioLevel(attempt);
        attempt.level = level;
        if (level >= silenceThreshold) {
          attempt.lastAudibleAt = currentTime;
          attempt.silenceMs = 0;
        } else {
          attempt.silenceMs = Math.max(0, currentTime - attempt.lastAudibleAt);
        }
        emit();
        if (
          silenceAutoStop &&
          attempt.elapsedMs >= minRecordingMs + silenceGraceMs &&
          attempt.silenceMs >= silenceAfterMs
        ) {
          stop({ force: true, reason: "silence" });
        }
      }, meterIntervalMs);
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
      beginAudioMeter(attempt);
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
        options.onRecordingReady(blob, {
          attemptId: attempt.id,
          elapsedMs: attempt.elapsedMs,
          mimeType: attempt.mimeType,
          signal: attempt.controller.signal,
        });
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
          finishError(attempt, error && error.name === "AbortError" ? "전사가 취소되었습니다." : error && error.message ? error.message : "전사에 실패했습니다. 다시 시도해 주세요.");
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
        meterTimerId: null,
        stopRequested: false,
        finalized: false,
        cleaned: false,
        level: 0,
        silenceMs: 0,
        lastAudibleAt: null,
        audioContext: null,
        analyser: null,
        audioBuffer: null,
        sourceNode: null,
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
      transition("stopping", config.reason === "silence" ? "말이 멈춘 것으로 감지해 녹음을 마무리합니다." : "녹음 마무리 중입니다…");
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
          level: activeAttempt ? activeAttempt.level : 0,
          silenceMs: activeAttempt ? activeAttempt.silenceMs : 0,
          silenceAutoStop: silenceAutoStop,
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
  root.createVoiceApi = createVoiceApi;
  root.VOICE_RECORDING_STATES = STATES.slice();
})(typeof window !== "undefined" ? window : globalThis);
