// 바닐라 JS 채팅 클라이언트 — 빌드 도구 없음.
(function () {
  "use strict";

  var SESSION_KEY = "lmwiki_session_id";
  var SESSION_TOKEN_KEY = "lmwiki_session_token";
  var CONSENT_KEY = "lmwiki_consent_version";
  var PARTICIPANT_TICKET_KEY = "lmwiki_participant_ticket";
  var PARTICIPANT_KEY = "lmwiki_participant_id";
  var MANAGEMENT_ID_PATTERN = /^[A-Za-z0-9._-]{1,128}$/;
  var MAX_TURNS = 10;
  var MAX_MESSAGE_LEN = 2000;
  var CONTEXTUAL_REPLIES = {
    track: [
      ["정서", "정서적인 어려움에 가까워요."],
      ["관계", "가족이나 대인관계의 어려움에 가까워요."],
      ["중독 관련", "중독 문제로 도움받을 전문기관을 찾고 있어요."],
      ["안전 위기", "자해나 자살 생각처럼 안전이 걱정돼요."]
    ],
    symptom_context: [
      ["최근 시작했어요", "최근 한 달 사이 시작됐어요."],
      ["몇 달 이상 됐어요", "몇 달 전부터 계속되고 있어요."],
      ["일상에 영향이 커요", "잠이나 일상생활에 영향을 많이 주고 있어요."]
    ],
    relationship_target: [
      ["가족·부부 관계", "가족이나 배우자와의 관계예요."],
      ["친구·직장 관계", "친구나 직장 동료와의 관계예요."]
    ],
    relationship_duration: [
      ["최근 시작했어요", "최근 시작된 관계 문제예요."],
      ["몇 달 이상 됐어요", "몇 달 전부터 이어지고 있어요."],
      ["일상에 영향이 커요", "잠이나 일상생활에도 영향을 받고 있어요."]
    ],
    crisis_plan_means: [
      ["현재 계획 없음", "지금 당장 실행할 구체적인 계획이나 수단은 없어요."],
      ["계획·수단 있음", "지금 실행할 계획이나 사용할 수단이 있어요."]
    ],
    crisis_attempt_history: [
      ["시도 이력 없음", "이전에 시도한 적은 없어요."],
      ["시도 이력 있음", "예전에 스스로를 해치려고 시도한 적이 있어요."]
    ],
    coping: [
      ["쉬면서 버텼어요", "집에서 쉬거나 버티면서 지냈어요."],
      ["병원·상담을 찾아봤어요", "병원이나 상담을 알아봤어요."],
      ["아직 해본 게 없어요", "아직 특별히 해본 방법은 없어요."]
    ],
    support: [
      ["가족·친구가 있어요", "가족이나 친구가 알고 도와주고 있어요."],
      ["혼자 감당 중", "지금은 대부분 혼자 감당하고 있어요."]
    ],
    expectation: [
      ["마음이 편해지고 싶어요", "상담을 통해 마음이 조금 편해지고 싶어요."],
      ["상황을 정리하고 싶어요", "상황을 정리하고 다음 방법을 찾고 싶어요."],
      ["방법을 찾고 싶어요", "상담에서 다음 방법을 함께 찾고 싶어요."]
    ]
  };
  var QUESTION_SLOT_HINTS = {
    symptom_context: [
      "언제부터",
      "얼마나 오래",
      "얼마 동안",
      "기간",
      "시작된",
      "시작됐",
      "지속",
      "일상에 어떤 영향",
      "잠이나 일"
    ],
    relationship_target: [
      "관계 대상",
      "누구와의 관계",
      "가족과",
      "연인과",
      "배우자와",
      "친구와",
      "직장 동료"
    ],
    relationship_duration: [
      "언제부터",
      "얼마나 오래",
      "얼마 동안",
      "기간",
      "시작된",
      "시작됐",
      "지속",
      "일상에 어떤 영향",
      "잠이나 일"
    ],
    coping: ["해본 방법", "대처해", "어떻게 버텼", "시도해", "해보신", "어떤 방법"],
    support: ["도와주는 사람", "지지해", "누구에게 말", "혼자 감당"],
    expectation: ["상담에서 어떤 도움", "기대하", "원하는 도움", "무엇을 얻"]
  };
  var GREETING =
    "안녕하세요. 첫 상담 전 접수면담입니다. 내용은 기본적으로 비밀로 다루지만, " +
    "자신이나 타인에게 즉각적인 위험이 있거나 학대·법적 요청이 있는 경우에는 안전을 위해 공유될 수 있습니다. " +
    "오늘 상담을 받으러 오신 가장 큰 이유를 편하게 말씀해 주세요.";
  var COACHING_GREETING =
    "안녕하세요. 질문이나 막힌 문제를 가져오시면 관련 지식과 풀이 과정을 함께 살펴볼게요.";
  var greetingText = COACHING_GREETING;
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
  var contextualRepliesEl = document.getElementById("contextual-replies");
  var resetSessionEl = document.getElementById("reset-session");
  var characterCountEl = document.getElementById("character-count");
  var coachingStatusEl = document.getElementById("coaching-status");
  var coachingStageEl = document.getElementById("coaching-stage");
  var coachingNextActionEl = document.getElementById("coaching-next-action");
  // 스테퍼/칩 공유 게이트 — 기본 false(fail-closed). /api/config가
  // {intake_schema: true}를 확인해줄 때만 true로 승격한다. Phase 4 칩도 이 값을 쓴다.
  var intakeSchemaActive = false;
  // 첫 턴 여부 — 칩 노출 조건(intakeSchemaActive && 발화 0회)의 두 번째 축.
  var userHasSpoken = false;
  var requestPending = false;
  var configReady = false;
  var consentRequired = false;
  var consentGranted = false;
  var privacy = null;
  var consentCardEl = document.getElementById("consent-card");
  var deleteSessionEl = document.getElementById("delete-session");
  var deleteCodeCardEl = document.getElementById("delete-code-card");
  var deleteCodeValueEl = document.getElementById("delete-code-value");
  var previousDeleteEl = document.getElementById("previous-delete");
  var acceptEl = document.getElementById("consent-accept");
  var declineEl = document.getElementById("consent-decline");

  function getSessionId() {
    var id = sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }

  function getParticipantId() {
    var url = new URL(window.location.href);
    var linkedId = url.searchParams.get("management_id") || url.searchParams.get("client_id") || "";
    var storedId = localStorage.getItem(PARTICIPANT_KEY);

    if (linkedId && MANAGEMENT_ID_PATTERN.test(linkedId)) {
      if (storedId !== linkedId) {
        localStorage.setItem(PARTICIPANT_KEY, linkedId);
        sessionStorage.removeItem(SESSION_KEY);
        sessionStorage.removeItem(SESSION_TOKEN_KEY);
        sessionStorage.removeItem(CONSENT_KEY);
        localStorage.removeItem(PARTICIPANT_TICKET_KEY);
      }
      url.searchParams.delete("management_id");
      url.searchParams.delete("client_id");
      window.history.replaceState({}, "", url.pathname + url.search + url.hash);
      return linkedId;
    }

    if (!storedId) {
      storedId = crypto.randomUUID();
      localStorage.setItem(PARTICIPANT_KEY, storedId);
    }
    return storedId;
  }

  function getSessionToken() {
    return sessionStorage.getItem(SESSION_TOKEN_KEY) || "";
  }

  function formatTimestamp(date) {
    return date.toLocaleTimeString("ko-KR", { hour: "numeric", minute: "2-digit" });
  }

  var SUPPORT_PHONE_LINKS = {
    "109": "tel:109",
    "119": "tel:119",
    "129": "tel:129",
    "1336": "tel:1336",
    "1342": "tel:1342",
    "1388": "tel:1388",
    "1577-0199": "tel:15770199",
    "1588-9191": "tel:15889191",
    "1599-0075": "tel:15990075",
    "000-000-0000": "tel:0000000000"
  };
  var SUPPORT_LINK_PATTERN = /(https:\/\/[^\s]+|000-000-0000|1588-9191|1577-0199|1599-0075|(?:^|[^\d])(109|119|129|1336|1342|1388)(?!\d))/g;

  function appendSupportLinks(node, content) {
    node.textContent = "";
    var cursor = 0;
    content.replace(SUPPORT_LINK_PATTERN, function (match, _url, shortNumber, offset) {
      var leading = "";
      var value = match;
      if (shortNumber && match !== shortNumber) {
        leading = match.slice(0, -shortNumber.length);
        value = shortNumber;
      }
      node.appendChild(document.createTextNode(content.slice(cursor, offset) + leading));
      var link = document.createElement("a");
      link.className = "support-link";
      link.textContent = value;
      if (value.startsWith("https://")) {
        link.href = value.replace(/[),.;]+$/, "");
        link.target = "_blank";
        link.rel = "noopener noreferrer";
      } else {
        link.href = SUPPORT_PHONE_LINKS[value];
        link.setAttribute("aria-label", value + " 전화 걸기");
      }
      node.appendChild(link);
      cursor = offset + match.length;
      return match;
    });
    node.appendChild(document.createTextNode(content.slice(cursor)));
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
    return { row: row, bubble: bubble, time: time, col: col };
  }

  function setStatus(text) {
    statusEl.textContent = text || "";
  }

  var typingEl = null;

  function showTyping() {
    typingEl = document.createElement("li");
    typingEl.className = "message-row message-row-assistant typing-row";

    var avatar = document.createElement("span");
    avatar.className = "avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.innerHTML = BOT_AVATAR_SVG;

    var bubble = document.createElement("div");
    bubble.className = "message message-assistant typing";
    bubble.setAttribute("aria-label", "답변을 준비하고 있습니다");
    for (var i = 0; i < 3; i++) {
      var dot = document.createElement("span");
      dot.className = "dot";
      bubble.appendChild(dot);
    }
    typingEl.appendChild(avatar);
    typingEl.appendChild(bubble);
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
          appendSupportLinks(bubble, text);
          resolve(rendered);
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

  window.lmwikiChooseReplySlot = function (intake, reply) {
    var unfilled = intake && Array.isArray(intake.unfilled) ? intake.unfilled : [];
    if (!unfilled.length) return null;

    var normalizedReply = String(reply || "").replace(/\s+/g, " ");
    var hintedSlotIds = Object.keys(QUESTION_SLOT_HINTS).filter(function (slotId) {
      return QUESTION_SLOT_HINTS[slotId].some(function (hint) {
        return normalizedReply.indexOf(hint) !== -1;
      });
    });
    var hintedUnfilled = unfilled.filter(function (slot) {
      return hintedSlotIds.indexOf(slot.id) !== -1;
    });

    if (hintedUnfilled.length) return hintedUnfilled[0].id;
    if (hintedSlotIds.length) return null;
    return unfilled[0].id;
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
    if (chipsEl && intakeSchemaActive && !userHasSpoken && configReady && (!consentRequired || consentGranted)) {
      chipsEl.hidden = false;
    }
  }

  function autoResizeInput() {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + "px";
  }

  function updateInputState() {
    var length = inputEl.value.length;
    if (characterCountEl) {
      characterCountEl.textContent = length + "/" + MAX_MESSAGE_LEN;
      characterCountEl.classList.toggle("near-limit", length > MAX_MESSAGE_LEN * 0.85);
    }
    sendButtonEl.disabled = requestPending || inputEl.disabled || !inputEl.value.trim();
    autoResizeInput();
  }

  function hideContextualReplies() {
    if (!contextualRepliesEl) return;
    contextualRepliesEl.hidden = true;
    contextualRepliesEl.textContent = "";
  }

  function renderContextualReplies(intake, reply) {
    hideContextualReplies();
    if (!contextualRepliesEl || !intake || !intake.unfilled || !intake.unfilled.length) return;

    var nextSlotId = window.lmwikiChooseReplySlot(intake, reply);
    if (!nextSlotId) return;
    var nextSlot = intake.unfilled.find(function (slot) {
      return slot.id === nextSlotId;
    });
    if (!nextSlot) return;
    var suggestions = CONTEXTUAL_REPLIES[nextSlot.id];
    if (!suggestions || !suggestions.length) return;

    suggestions.forEach(function (suggestion) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "reply-suggestion" + (nextSlot.red_flag ? " reply-suggestion-alert" : "");
      button.textContent = suggestion[0];
      button.setAttribute("data-send", suggestion[1]);
      button.addEventListener("click", function () {
        sendMessage(suggestion[1]);
      });
      contextualRepliesEl.appendChild(button);
    });
    contextualRepliesEl.hidden = false;
  }

  function renderServerQuickReplies(replies) {
    if (!contextualRepliesEl || !Array.isArray(replies) || !replies.length) return;
    hideContextualReplies();
    replies.forEach(function (reply) {
      if (!reply || !reply.label || !reply.message) return;
      var button = document.createElement("button");
      button.type = "button";
      button.className = "reply-suggestion";
      button.textContent = reply.label;
      button.addEventListener("click", function () {
        sendMessage(reply.message);
      });
      contextualRepliesEl.appendChild(button);
    });
    contextualRepliesEl.hidden = false;
  }

  function renderCoachingStatus(data) {
    if (!coachingStatusEl || !data || typeof data.coach_stage !== "string" || typeof data.next_action !== "string") return;
    coachingStageEl.textContent = data.coach_stage;
    coachingNextActionEl.textContent = "다음 행동: " + data.next_action;
    coachingStatusEl.hidden = false;
  }

  function resetSession() {
    if (requestPending) return;
    sessionStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(SESSION_TOKEN_KEY);
    sessionStorage.removeItem(CONSENT_KEY);
    consentGranted = false;
    deleteSessionEl.hidden = true;
    deleteCodeCardEl.hidden = true;
    deleteCodeValueEl.textContent = "";
    getSessionId();
    userHasSpoken = false;
    inputEl.disabled = !configReady || consentRequired;
    inputEl.value = "";
    messagesEl.textContent = "";
    slotListEl.textContent = "";
    panelEl.hidden = true;
    if (coachingStatusEl) coachingStatusEl.hidden = true;
    if (coachingStageEl) coachingStageEl.textContent = "";
    if (coachingNextActionEl) coachingNextActionEl.textContent = "";
    hideContextualReplies();
    setStatus("");
    updateTurnCounter(0);
    setActiveStep(1);
    if (consentRequired) {
      showConsent();
    } else if (configReady) {
      addMessage("assistant", greetingText);
    }
    maybeShowChips();
    updateInputState();
    inputEl.focus();
  }

  function sendMessage(message, options) {
    options = options || {};
    if (requestPending || !configReady || (consentRequired && !consentGranted) || inputEl.disabled) return;
    message = String(message || "").trim().slice(0, MAX_MESSAGE_LEN);
    if (!message) return;

    requestPending = true;
    userHasSpoken = true;
    hideChips();
    hideContextualReplies();
    setStatus("방금 입력을 읽고 있어요…");
    addMessage("user", message);
    if (!options.preserveInput) inputEl.value = "";
    if (resetSessionEl) resetSessionEl.disabled = true;
    updateInputState();
    showTyping();

    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: getSessionId(),
        session_token: getSessionToken() || null,
        participant_id: getParticipantId(),
        participant_ticket: localStorage.getItem(PARTICIPANT_TICKET_KEY) || null,
        message: message,
      }),
    })
      .then(function (response) {
        if (response.ok) return response.json();

        hideTyping();
        if (response.status === 409 || response.status === 401) disableInput();
        response.json().then(function (error) {
          setStatus(error.detail || "오류가 발생했습니다. 새 대화로 시작해 주세요.");
        });
        requestPending = false;
        if (resetSessionEl) resetSessionEl.disabled = false;
        updateInputState();
        return null;
      })
      .then(function (data) {
        if (!data) return;

        hideTyping();
        rememberCredentials(data);
        deleteSessionEl.hidden = !getSessionToken();
        // fake 모드 진행 접미사(" | 채움: ..")는 패널이 대신 보여주므로 표시에서만 제거.
        var replyText = data.reply.replace(/ \| (채움|다음 질문): .*$/, "");
        setStatus("답변을 작성하고 있어요…");
        typeAssistantMessage(replyText).then(function () {
          setStatus("");
          updateTurnCounter(data.turn);
          renderIntake(data.intake);
          if (Array.isArray(data.quick_replies) && data.quick_replies.length) {
            renderServerQuickReplies(data.quick_replies);
          } else {
            renderContextualReplies(data.intake, replyText);
          }
          renderCoachingStatus(data);
          requestPending = false;
          if (resetSessionEl) resetSessionEl.disabled = false;

          if (data.conversation_ended) {
            setStatus("안내가 완료되어 대화가 종료되었습니다. 다시 시작하려면 ‘새 대화’를 눌러 주세요.");
            hideContextualReplies();
            disableInput();
            return;
          }
          if (data.limit_reached) {
            setStatus("대화 한도에 도달했습니다. 새 세션으로 다시 시작해 주세요.");
            hideContextualReplies();
            disableInput();
            return;
          }

          updateInputState();
          inputEl.focus();
        });
      })
      .catch(function () {
        hideTyping();
        setStatus("네트워크 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.");
        requestPending = false;
        if (resetSessionEl) resetSessionEl.disabled = false;
        updateInputState();
      });
  }

  formEl.addEventListener("submit", function (event) {
    event.preventDefault();
    var message = inputEl.value.trim();
    if (!message) return;
    sendMessage(message);
  });

  inputEl.addEventListener("input", updateInputState);
  inputEl.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      formEl.requestSubmit();
    }
  });

  if (resetSessionEl) {
    resetSessionEl.addEventListener("click", resetSession);
  }

  if (chipsEl) {
    chipsEl.querySelectorAll(".chip").forEach(function (button) {
      button.addEventListener("click", function () {
        sendMessage(button.getAttribute("data-send"));
      });
    });
  }

  function setTextIf(selector, value) {
    if (!value) return;
    var el = document.querySelector(selector);
    if (el) el.textContent = value;
  }

  // 스키마 소유 UI 문구 적용 — 제공된 키만 덮어쓰고 나머지는 정적 기본(상담) 문구 유지.
  function applyUiConfig(ui) {
    if (!ui || typeof ui !== "object") return;
    if (ui.greeting) greetingText = ui.greeting;
    if (ui.title) {
      document.title = ui.title;
      setTextIf(".chat-title h1", ui.title);
    }
    setTextIf(".subtitle", ui.subtitle);
    setTextIf(".privacy-summary-text", ui.privacy_summary);
    setTextIf(".privacy-body", ui.privacy_body);
    setTextIf(".panel-title", ui.panel_title);
    setTextIf(".lock-notice-text", ui.lock_notice);
    if (Array.isArray(ui.stepper_labels)) {
      document.querySelectorAll(".stepper-label").forEach(function (el, i) {
        if (ui.stepper_labels[i]) el.textContent = ui.stepper_labels[i];
      });
    }
    if (ui.contextual_replies && typeof ui.contextual_replies === "object") {
      CONTEXTUAL_REPLIES = ui.contextual_replies;
    }
    if (Array.isArray(ui.chips) && chipsEl) {
      chipsEl.textContent = "";
      ui.chips.forEach(function (chip) {
        if (!chip || !chip.send) return;
        var button = document.createElement("button");
        button.type = "button";
        button.className = "chip";
        button.setAttribute("data-send", chip.send);
        var title = document.createElement("span");
        title.className = "chip-title";
        title.textContent = chip.title || chip.send;
        button.appendChild(title);
        if (chip.desc) {
          var desc = document.createElement("span");
          desc.className = "chip-desc";
          desc.textContent = chip.desc;
          button.appendChild(desc);
        }
        button.addEventListener("click", function () {
          sendMessage(chip.send);
        });
        chipsEl.appendChild(button);
      });
    }
  }

  function applyCoachingMode() {
    greetingText = COACHING_GREETING;
    document.title = "학습 코칭 챗봇";
    setTextIf(".chat-title h1", "학습 코칭 챗봇");
    setTextIf(".subtitle", "질문과 지식 문서를 바탕으로 함께 살펴봅니다");
    setTextIf(".privacy-summary-text", "학습 대화 안내");
    setTextIf(
      ".privacy-body",
      "대화 내용은 학습 흐름을 이어가기 위해 저장될 수 있습니다. 이름, 연락처, 학교명 같은 개인정보는 입력하지 마세요."
    );
    setTextIf(".lock-notice-text", "대화 내용은 학습 흐름을 이어가기 위해 저장될 수 있습니다");
    if (panelEl) panelEl.hidden = true;
    if (stepperEl) stepperEl.hidden = true;
    if (chipsEl) chipsEl.hidden = true;
    intakeSchemaActive = false;
  }

  function applyIntakeMode() {
    greetingText = GREETING;
    document.title = "접수 면담 챗봇";
    setTextIf(".chat-title h1", "접수 면담 챗봇");
    setTextIf(".subtitle", "첫 상담 전, 이야기를 정리하는 시간입니다");
    setTextIf(".privacy-summary-text", "첫 상담 전 접수용 안내");
    setTextIf(
      ".privacy-body",
      "대화 내용은 서버에 저장됩니다. 자·타해 위험, 학대 의심, 법적 요청처럼 안전 예외가 있는 경우에는 보호자·전문기관과 공유될 수 있습니다."
    );
    setTextIf(".lock-notice-text", "접수 내용은 저장되며 안전 예외가 있습니다");
  }

  function rememberCredentials(data) {
    if (data.session_token) sessionStorage.setItem(SESSION_TOKEN_KEY, data.session_token);
    if (data.participant_id) localStorage.setItem(PARTICIPANT_KEY, data.participant_id);
    if (data.participant_ticket) localStorage.setItem(PARTICIPANT_TICKET_KEY, data.participant_ticket);
  }

  function showConsent() {
    consentCardEl.hidden = false;
    document.getElementById("consent-notice").textContent = privacy.body;
    document.getElementById("consent-version").textContent = "고지 버전: " + privacy.consent_version;
    disableInput();
    hideChips();
    hideContextualReplies();
  }

  function postJson(url, payload) {
    return fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }).then(function (response) {
      return response.json().then(function (data) {
        if (!response.ok) throw new Error(data.detail || "처리하지 못했습니다.");
        return data;
      });
    });
  }

  function chooseConsent(accepted) {
    if (requestPending || !privacy) return;
    requestPending = true;
    acceptEl.disabled = true;
    declineEl.disabled = true;
    resetSessionEl.disabled = true;
    postJson("/api/consent", {
      session_id: getSessionId(), accepted: accepted, consent_version: privacy.consent_version
    }).then(function (data) {
      consentCardEl.hidden = true;
      if (!data.accepted) {
        var refusal = addMessage("assistant", data.reply);
        appendSupportLinks(refusal.bubble, data.reply);
        disableInput();
        return;
      }
      rememberCredentials(data);
      sessionStorage.setItem(CONSENT_KEY, privacy.consent_version);
      consentGranted = true;
      deleteCodeValueEl.textContent = data.delete_code;
      deleteCodeCardEl.hidden = false;
      deleteSessionEl.hidden = false;
      inputEl.disabled = false;
      addMessage("assistant", data.reply);
      maybeShowChips();
      inputEl.focus();
    }).catch(function (error) {
      setStatus(error.message);
    }).finally(function () {
      requestPending = false;
      acceptEl.disabled = false;
      declineEl.disabled = false;
      resetSessionEl.disabled = false;
      updateInputState();
    });
  }

  acceptEl.addEventListener("click", function () { chooseConsent(true); });
  declineEl.addEventListener("click", function () { chooseConsent(false); });
  document.getElementById("copy-delete-code").addEventListener("click", function () {
    if (!navigator.clipboard) {
      setStatus("화면의 삭제 코드를 선택해 복사하거나 적어 두세요.");
      return;
    }
    navigator.clipboard.writeText(deleteCodeValueEl.textContent).then(function () {
      setStatus("삭제 코드를 복사했습니다.");
    }).catch(function () { setStatus("화면의 삭제 코드를 선택해 복사하거나 적어 두세요."); });
  });

  function deleteRecords(payload) {
    if (requestPending) return;
    requestPending = true;
    deleteSessionEl.disabled = true;
    resetSessionEl.disabled = true;
    acceptEl.disabled = true;
    declineEl.disabled = true;
    updateInputState();
    return postJson("/api/session/delete", payload).then(function (data) {
      if (data.session_id === sessionStorage.getItem(SESSION_KEY)) {
        requestPending = false;
        resetSession();
        requestPending = true;
      }
      document.getElementById("delete-status").textContent = data.reply;
      document.getElementById("delete-code-input").value = "";
    }).catch(function (error) {
      document.getElementById("delete-status").textContent = error.message;
    }).finally(function () {
      requestPending = false;
      deleteSessionEl.disabled = false;
      resetSessionEl.disabled = false;
      acceptEl.disabled = false;
      declineEl.disabled = false;
      updateInputState();
    });
  }

  deleteSessionEl.addEventListener("click", function () {
    if (requestPending || !getSessionToken()) return;
    if (!window.confirm("이 대화의 원문과 요약을 모두 지울까요?")) return;
    deleteRecords({session_id: getSessionId(), session_token: getSessionToken()});
  });
  document.getElementById("delete-code-form").addEventListener("submit", function (event) {
    event.preventDefault();
    var code = document.getElementById("delete-code-input").value.trim();
    if (code) deleteRecords({delete_code: code});
  });

  // 예약 링크의 관리번호를 첫 발화 전에 확정하고 URL에서는 즉시 제거한다.
  getParticipantId();

  // 스테퍼 게이트 프로브 — 실패/비정상 응답은 기본값(false, hidden 유지)에 머물러
  // fail-closed로 수렴한다. 채팅 기능에는 영향 없음. 첫 인사말은 ui.greeting
  // 교체 가능성 때문에 프로브가 끝난 뒤(성공·실패 공통) 표시한다.
  fetch("/api/config")
    .then(function (response) {
      if (!response.ok) throw new Error("config fetch failed: " + response.status);
      return response.json();
    })
    .then(function (data) {
      if (data && data.mode === "coaching") applyCoachingMode();
      if (data && data.mode === "intake") applyIntakeMode();
      applyUiConfig(data && data.ui);
      configReady = true;
      consentRequired = data.consent_required === true;
      privacy = data.privacy;
      if (consentRequired) {
        if (!privacy || !privacy.body || !privacy.consent_version) throw new Error("privacy config missing");
        previousDeleteEl.hidden = false;
        setTextIf(".privacy-body", privacy.body);
        greetingText = (data.ui.intro || "") + " " + (data.opening_question || "");
        consentGranted = getSessionToken() && sessionStorage.getItem(CONSENT_KEY) === privacy.consent_version;
        if (!consentGranted) showConsent();
      }
      inputEl.disabled = consentRequired && !consentGranted;
      deleteSessionEl.hidden = !getSessionToken();
      if (data && data.mode === "intake" && data.intake_schema === true) {
        intakeSchemaActive = true;
        if (stepperEl) stepperEl.hidden = false;
        setActiveStep(1);
        maybeShowChips();
      }
    })
    .catch(function (err) {
      configReady = false;
      disableInput();
      hideChips();
      setStatus("이용 안내를 불러오지 못했습니다. 새로고침해 주세요. 긴급 도움: 109 · 1588-9191 · 119");
      console.warn("intake config probe failed; stepper stays hidden", err);
    })
    .finally(function () {
      if (configReady && (!consentRequired || consentGranted)) addMessage("assistant", greetingText);
      updateInputState();
    });

  updateInputState();
})();
