// 바닐라 JS 채팅 클라이언트 — 빌드 도구 없음.
(function () {
  "use strict";

  var SESSION_KEY = "lmwiki_session_id";
  var PARTICIPANT_KEY = "lmwiki_participant_id";
  var MAX_TURNS = 10;
  var GREETING =
    "안녕하세요. 첫 상담 전 접수면담입니다. 내용은 기본적으로 비밀로 다루지만, " +
    "자신이나 타인에게 즉각적인 위험이 있거나 학대·법적 요청이 있는 경우에는 안전을 위해 공유될 수 있습니다. " +
    "오늘 상담을 받으러 오신 가장 큰 이유를 편하게 말씀해 주세요.";
  var BOT_AVATAR_SVG =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">' +
    '<rect x="5" y="8" width="14" height="11" rx="3"></rect>' +
    '<circle cx="9.5" cy="13.5" r="1.3" fill="currentColor" stroke="none"></circle>' +
    '<circle cx="14.5" cy="13.5" r="1.3" fill="currentColor" stroke="none"></circle>' +
    '<path d="M12 8V5"></path><circle cx="12" cy="4" r="1"></circle>' +
    '<path d="M9 19v2M15 19v2"></path></svg>';

  var messagesEl = document.getElementById("messages");
  var statusEl = document.getElementById("status");
  var turnCounterEl = document.getElementById("turn-counter");
  var formEl = document.getElementById("chat-form");
  var inputEl = document.getElementById("message-input");
  var sendButtonEl = document.getElementById("send-button");
  var panelEl = document.getElementById("intake-panel");
  var slotListEl = document.getElementById("slot-list");
  var stepperEl = document.getElementById("stepper");
  var chipsEl = document.getElementById("chips");

  // 스테퍼/칩 공유 게이트 — 기본 false(fail-closed). /api/config가
  // {intake_schema: true}를 확인해줄 때만 true로 승격한다. Phase 4 칩도 이 값을 쓴다.
  var intakeSchemaActive = false;
  // 첫 턴 여부 — 칩 노출 조건(intakeSchemaActive && 발화 0회)의 두 번째 축.
  var userHasSpoken = false;

  function getSessionId() {
    var id = sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }

  function getParticipantId() {
    var id = localStorage.getItem(PARTICIPANT_KEY);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(PARTICIPANT_KEY, id);
    }
    return id;
  }

  function formatTimestamp(date) {
    return date.toLocaleTimeString("ko-KR", { hour: "numeric", minute: "2-digit" });
  }

  function addMessage(role, text) {
    var row = document.createElement("li");
    row.className = "message-row message-row-" + role;

    if (role === "assistant") {
      var avatar = document.createElement("span");
      avatar.className = "avatar";
      avatar.setAttribute("aria-hidden", "true");
      avatar.innerHTML = BOT_AVATAR_SVG;
      row.appendChild(avatar);
    }

    var col = document.createElement("div");
    col.className = "bubble-col";

    var bubble = document.createElement("div");
    bubble.className = "message message-" + role;
    bubble.textContent = text;
    col.appendChild(bubble);

    var time = document.createElement("span");
    time.className = "message-time";
    time.textContent = formatTimestamp(new Date());
    col.appendChild(time);

    row.appendChild(col);
    messagesEl.appendChild(row);
    row.scrollIntoView({ block: "nearest" });
    return { row: row, bubble: bubble, time: time };
  }

  function setStatus(text) {
    statusEl.textContent = text || "";
  }

  var typingEl = null;

  function showTyping() {
    typingEl = document.createElement("li");
    typingEl.className = "message message-assistant typing";
    for (var i = 0; i < 3; i++) {
      var dot = document.createElement("span");
      dot.className = "dot";
      typingEl.appendChild(dot);
    }
    messagesEl.appendChild(typingEl);
    typingEl.scrollIntoView({ block: "nearest" });
  }

  function hideTyping() {
    if (typingEl) {
      typingEl.remove();
      typingEl = null;
    }
  }


  function typeAssistantMessage(text) {
    var rendered = addMessage("assistant", "");
    var bubble = rendered.bubble;
    var reducedMotion =
      window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var step = reducedMotion ? text.length : 3;
    var delay = reducedMotion ? 0 : 14;
    var index = 0;

    return new Promise(function (resolve) {
      function tick() {
        index = Math.min(index + step, text.length);
        bubble.textContent = text.slice(0, index);
        rendered.row.scrollIntoView({ block: "nearest" });
        if (index < text.length) {
          window.setTimeout(tick, delay);
        } else {
          resolve();
        }
      }
      tick();
    });
  }

  function slotItem(state, label, value, isNext, redFlag) {
    var li = document.createElement("li");
    li.className =
      "slot slot-" + state + (isNext ? " slot-next" : "") + (redFlag ? " slot-redflag" : "");
    var name = document.createElement("span");
    name.className = "slot-label";
    name.textContent = label;
    li.appendChild(name);
    if (value) {
      var val = document.createElement("span");
      val.className = "slot-value";
      val.textContent = value;
      li.appendChild(val);
    } else if (isNext) {
      var badge = document.createElement("span");
      badge.className = "slot-badge";
      badge.textContent = "다음 질문";
      li.appendChild(badge);
    }
    return li;
  }

  // 파생 규칙 — DOM 무접근 순수 함수. unfilledIds: intake.unfilled의 id 배열.
  window.lmwikiDeriveStep = function (unfilledIds) {
    var ids = unfilledIds || [];
    if (ids.indexOf("track") !== -1) return 1;
    var remaining = ids.filter(function (id) {
      return id !== "expectation";
    });
    return remaining.length > 0 ? 2 : 3;
  };

  function setActiveStep(step) {
    if (!stepperEl) return;
    stepperEl.querySelectorAll(".stepper-step").forEach(function (el, i) {
      var stepNum = i + 1;
      el.classList.toggle("active", stepNum === step);
      el.classList.toggle("done", stepNum < step);
    });
  }

  // intake 필드는 스키마 활성 지식셋에서만 온다 — 없으면(스왑 지식셋) 패널 숨김 유지.
  function renderIntake(intake) {
    if (!intake) return;
    panelEl.hidden = false;
    slotListEl.textContent = "";
    intake.filled.forEach(function (slot) {
      slotListEl.appendChild(slotItem("filled", slot.label, slot.value, false, false));
    });
    intake.unfilled.forEach(function (slot, i) {
      slotListEl.appendChild(slotItem("unfilled", slot.label, null, i === 0, slot.red_flag));
    });
    if (intakeSchemaActive) {
      var unfilledIds = intake.unfilled.map(function (slot) {
        return slot.id;
      });
      setActiveStep(window.lmwikiDeriveStep(unfilledIds));
    }
  }

  function updateTurnCounter(turn) {
    turnCounterEl.textContent = turn + "/" + MAX_TURNS;
    var progressEl = document.getElementById("turn-progress");
    if (progressEl) {
      progressEl.style.width = (turn / MAX_TURNS) * 100 + "%";
    }
  }

  function disableInput() {
    inputEl.disabled = true;
    sendButtonEl.disabled = true;
  }

  function hideChips() {
    if (chipsEl) chipsEl.hidden = true;
  }

  function maybeShowChips() {
    if (chipsEl && intakeSchemaActive && !userHasSpoken) {
      chipsEl.hidden = false;
    }
  }

  function sendMessage(message) {
    userHasSpoken = true;
    hideChips();
    setStatus("방금 입력을 읽고 있어요…");
    addMessage("user", message);
    inputEl.value = "";
    sendButtonEl.disabled = true;
    showTyping();

    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: getSessionId(),
        participant_id: getParticipantId(),
        message: message,
      }),
    })
      .then(function (response) {
        if (response.ok) return response.json();

        hideTyping();
        setStatus(
          response.status === 429
            ? "이용 한도를 초과했습니다. 잠시 후 다시 시도해 주세요."
            : "오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        );
        sendButtonEl.disabled = false;
        return null;
      })
      .then(function (data) {
        if (!data) return;

        hideTyping();
        // fake 모드 진행 접미사(" | 채움: ..")는 패널이 대신 보여주므로 표시에서만 제거.
        var replyText = data.reply.replace(/ \| (채움|다음 질문): .*$/, "");
        setStatus("상담사가 답변을 작성하고 있어요…");
        typeAssistantMessage(replyText).then(function () {
          setStatus("");
          updateTurnCounter(data.turn);
          renderIntake(data.intake);

          if (data.limit_reached) {
            setStatus("대화 한도에 도달했습니다. 새 세션으로 다시 시작해 주세요.");
            disableInput();
            return;
          }

          sendButtonEl.disabled = false;
          inputEl.focus();
        });
      })
      .catch(function () {
        hideTyping();
        setStatus("네트워크 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.");
        sendButtonEl.disabled = false;
      });
  }

  formEl.addEventListener("submit", function (event) {
    event.preventDefault();
    var message = inputEl.value.trim();
    if (!message) return;
    sendMessage(message);
  });

  if (chipsEl) {
    chipsEl.querySelectorAll(".chip").forEach(function (button) {
      button.addEventListener("click", function () {
        sendMessage(button.getAttribute("data-send"));
      });
    });
  }

  // 스테퍼 게이트 프로브 — 실패/비정상 응답은 기본값(false, hidden 유지)에 머물러
  // fail-closed로 수렴한다. 채팅 기능에는 영향 없음.
  fetch("/api/config")
    .then(function (response) {
      if (!response.ok) throw new Error("config fetch failed: " + response.status);
      return response.json();
    })
    .then(function (data) {
      if (data && data.intake_schema === true) {
        intakeSchemaActive = true;
        if (stepperEl) stepperEl.hidden = false;
        setActiveStep(1);
        maybeShowChips();
      }
    })
    .catch(function (err) {
      console.warn("intake config probe failed; stepper stays hidden", err);
    });

  addMessage("assistant", GREETING);
})();
