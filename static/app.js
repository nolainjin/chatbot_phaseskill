// 바닐라 JS 채팅 클라이언트 — 빌드 도구 없음.
(function () {
  "use strict";

  var SESSION_KEY = "lmwiki_session_id";
  var SESSION_TOKEN_KEY = "lmwiki_session_token";
  var CONSENT_KEY = "lmwiki_consent_version";
  var PARTICIPANT_TICKET_KEY = "lmwiki_participant_ticket";
  var PARTICIPANT_KEY = "lmwiki_participant_id";
  var INTAKE_LINK_KEY = "lmwiki_pending_intake_link";
  var DRAFT_KEY = "lmwiki_message_draft";
  var PENDING_REQUEST_KEY = "lmwiki_pending_chat_request";
  var UI_STATE_KEY = "lmwiki_chat_ui_state";
  var institutionHash = new URL(window.location.href).hash;
  var institutionToken = institutionHash.indexOf("#intake=") === 0 ? institutionHash.slice(8) : null;
  if (institutionToken !== null) {
    window.history.replaceState({}, "", window.location.pathname + window.location.search);
    sessionStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(SESSION_TOKEN_KEY);
    sessionStorage.removeItem(CONSENT_KEY);
    sessionStorage.removeItem(DRAFT_KEY);
    sessionStorage.removeItem(PENDING_REQUEST_KEY);
    sessionStorage.removeItem(UI_STATE_KEY);
  }
  // Opening a second institution link in this same tab is a same-document
  // navigation. Re-enter initialization instead of retaining the previous case.
  if (typeof window.addEventListener === "function") window.addEventListener("hashchange", function () {
    if (new URL(window.location.href).hash.indexOf("#intake=") === 0) window.location.reload();
  });
  var MANAGEMENT_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9-]{0,31}$/;
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
  var deliveryStatusEl = document.getElementById("delivery-status");
  var deliveryHelpEl = document.getElementById("delivery-help");
  var deliveryProgressEl = document.getElementById("delivery-progress");
  var retryButtonEl = document.getElementById("retry-button");
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
  var institutionAccess = false;
  var consentGranted = false;
  var privacy = null;
  var consentCardEl = document.getElementById("consent-card");
  var deleteSessionEl = document.getElementById("delete-session");
  var deleteCodeCardEl = document.getElementById("delete-code-card");
  var deleteCodeValueEl = document.getElementById("delete-code-value");
  var previousDeleteEl = document.getElementById("previous-delete");
  var acceptEl = document.getElementById("consent-accept");
  var declineEl = document.getElementById("consent-decline");
  var handoffCardEl = null;
  var pendingRequest = null;
  var retryMessage = null;
  var retryMessageRequestId = null;

  function setDeliveryState(state, help) {
    if (state === "completed") state = "saved";
    var states = {
      ready: ["작성 준비", consentGranted ? "편하게 입력해 주세요. 아직 저장된 내용은 없습니다." : "동의 후 편하게 입력해 주세요. 아직 저장된 내용은 없습니다."],
      link_required: ["접수 링크 확인 필요", "센터에서 받은 개별 접수 링크로 열어 주세요."],
      draft: ["작성 중 · 임시 보관", "작성 중인 내용은 이 탭에만 임시 보관됩니다. 전송 버튼을 눌러야 접수 기록에 저장됩니다."],
      saved: ["저장됨", institutionAccess ? "보낸 대화는 접수 중에도 소속 센터의 권한 있는 담당자가 확인할 수 있어요." : "보낸 대화가 접수 기록에 저장되었습니다."],
      analyzing: ["분석 중", "입력 내용을 안전하게 저장하고 정리하고 있습니다."],
      confirmation_required: ["접수 완료 전 확인", "반영된 내용을 확인하거나 수정해 주세요. 전달 버튼을 누르면 접수 완료로 표시됩니다."],
      retryable: ["처리 다시 시도 필요", "입력은 보관되어 있습니다. 다시 시도하거나 내용을 수정해 주세요."],
      delivered: ["접수 완료", "접수 완료로 표시되었습니다. 상담사 검토 완료를 뜻하지는 않습니다."]
    };
    var entry = states[state] || states.ready;
    if (deliveryStatusEl) {
      deliveryStatusEl.textContent = entry[0];
      deliveryStatusEl.setAttribute("data-state", state === "analyzing" ? "processing" : state === "delivered" ? "delivered" : state === "confirmation_required" || state === "retryable" || state === "link_required" ? "attention" : "saved");
    }
    if (deliveryHelpEl) deliveryHelpEl.textContent = help || entry[1];
  }

  function saveDraft(value) {
    var text = String(value || "");
    if (text) sessionStorage.setItem(DRAFT_KEY, text);
    else sessionStorage.removeItem(DRAFT_KEY);
  }

  function rememberPending(request) {
    pendingRequest = request || null;
    if (request) sessionStorage.setItem(PENDING_REQUEST_KEY, JSON.stringify(request));
    else sessionStorage.removeItem(PENDING_REQUEST_KEY);
    if (retryButtonEl) retryButtonEl.hidden = !request;
  }

  function clearSensitiveTabState() {
    pendingRequest = null;
    sessionStorage.removeItem(PENDING_REQUEST_KEY);
    sessionStorage.removeItem(DRAFT_KEY);
    sessionStorage.removeItem(UI_STATE_KEY);
    if (retryButtonEl) retryButtonEl.hidden = true;
    inputEl.value = "";
    sessionStorage.removeItem(SESSION_TOKEN_KEY);
    sessionStorage.removeItem(CONSENT_KEY);
    consentGranted = false;
    messagesEl.textContent = "";
    retryMessage = null;
    retryMessageRequestId = null;
    slotListEl.textContent = "";
    panelEl.hidden = true;
    hideContextualReplies();
    if (coachingStatusEl) coachingStatusEl.hidden = true;
    handoffCardEl = null;
    deleteSessionEl.hidden = true;
    deleteCodeCardEl.hidden = true;
    deleteCodeValueEl.textContent = "";
  }

  function applyPendingState() {
    if (!pendingRequest || pendingRequest.session_id !== getSessionId()) return false;
    userHasSpoken = true;
    hideChips();
    inputEl.value = pendingRequest.message;
    inputEl.readOnly = false;
    if (!consentRequired || consentGranted) inputEl.disabled = false;
    if (retryButtonEl) retryButtonEl.hidden = false;
    setDeliveryState("retryable");
    return true;
  }

  function restorePending() {
    try {
      var request = JSON.parse(sessionStorage.getItem(PENDING_REQUEST_KEY));
      if (request && request.request_id && request.message && request.session_id === getSessionId()) {
        pendingRequest = request;
        applyPendingState();
        return;
      }
      sessionStorage.removeItem(PENDING_REQUEST_KEY);
    } catch (error) { sessionStorage.removeItem(PENDING_REQUEST_KEY); }
    inputEl.value = sessionStorage.getItem(DRAFT_KEY) || "";
    setDeliveryState(inputEl.value ? "draft" : "ready");
  }

  function rememberUiState(data) {
    try {
      var uiData = {
        reply: data.reply, turn: data.turn, intake: data.intake,
        quick_replies: data.quick_replies, closing: data.closing,
        handoff: data.handoff, processing_status: data.processing_status,
        conversation_ended: data.conversation_ended, limit_reached: data.limit_reached
      };
      sessionStorage.setItem(UI_STATE_KEY, JSON.stringify({session_id: getSessionId(), data: uiData}));
    } catch (error) { /* Chat can continue when tab storage is unavailable or full. */ }
  }

  function responseDeliveryState(data) {
    if (handoffDelivered(data.handoff)) return "delivered";
    if (data.processing_status === "retryable") return "retryable";
    if (data.closing) return "confirmation_required";
    return data.processing_status || "saved";
  }

  function handoffDelivered(handoff) {
    return Boolean(handoff && (handoff.sent === true || handoff.delivery_status === "sent_to_center"));
  }

  function restoreUiState() {
    var saved;
    try { saved = JSON.parse(sessionStorage.getItem(UI_STATE_KEY)); }
    catch (error) { sessionStorage.removeItem(UI_STATE_KEY); return false; }
    if (!saved || saved.session_id !== getSessionId() || !saved.data || !saved.data.reply) return false;
    var data = saved.data;
    userHasSpoken = true;
    hideChips();
    var restoredMessage = addMessage("assistant", data.reply.replace(/ \| (채움|다음 질문): .*$/, ""));
    if (data.processing_status === "retryable" || data.retryable === true) {
      retryMessage = restoredMessage;
      retryMessageRequestId = pendingRequest && pendingRequest.request_id;
    }
    updateTurnCounter(data.turn || 0);
    if (data.closing) turnCounterEl.textContent = "마지막 확인";
    if (handoffDelivered(data.handoff)) turnCounterEl.textContent = "전달 완료";
    renderIntake(data.intake);
    if (Array.isArray(data.quick_replies) && data.quick_replies.length) renderServerQuickReplies(data.quick_replies);
    renderCoachingStatus(data);
    renderHandoff(data.handoff);
    setDeliveryState(responseDeliveryState(data));
    if ((data.conversation_ended || data.limit_reached) && !pendingRequest) disableInput();
    return true;
  }

  function renderHandoff(handoff) {
    if (handoffCardEl) handoffCardEl.remove();
    handoffCardEl = null;
    if (!handoff || handoff.mode === "center") return;

    var card = document.createElement("li");
    card.className = "handoff-card";
    var title = document.createElement("h2");
    title.textContent = "기관에 전할 정리";
    card.appendChild(title);
    var note = Array.isArray(handoff.note) ? handoff.note.join("\n") : "";
    var noteEl = document.createElement("p");
    noteEl.className = "handoff-note";
    noteEl.textContent = note;
    card.appendChild(noteEl);

    var actions = document.createElement("div");
    actions.className = "handoff-actions";
    var feedback = document.createElement("p");
    feedback.setAttribute("role", "status");
    var copy = document.createElement("button");
    copy.type = "button";
    copy.textContent = "정리문 복사";
    copy.addEventListener("click", async function () {
      try {
        await navigator.clipboard.writeText(note);
        feedback.textContent = "정리문을 복사했어요.";
      } catch (error) {
        feedback.textContent = "복사하지 못했어요. 정리문을 선택해 복사하거나 내려받아 주세요.";
      }
    });
    actions.appendChild(copy);
    var download = document.createElement("button");
    download.type = "button";
    download.textContent = ".txt 내려받기";
    download.addEventListener("click", function () {
      var blob = new Blob([note + "\n"], { type: "text/plain;charset=utf-8" });
      var url = URL.createObjectURL(blob);
      var link = document.createElement("a");
      link.href = url;
      link.download = "기관에-전할-정리.txt";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      feedback.textContent = "정리문 내려받기를 시작했어요.";
    });
    actions.appendChild(download);
    card.appendChild(actions);
    card.appendChild(feedback);

    var places = document.createElement("h2");
    places.textContent = "연결할 수 있는 곳";
    card.appendChild(places);
    if (handoff.fallback_used) {
      var gap = document.createElement("p");
      gap.textContent = "가까운 기관을 아직 정리하지 못했어요";
      card.appendChild(gap);
      var guidance = document.createElement("p");
      guidance.textContent = "광역 단위 정신건강 상담 전화 1577-0199 또는 자살예방상담전화 109로 도움을 요청할 수 있어요.";
      card.appendChild(guidance);
    }
    (handoff.institutions || []).slice(0, 3).forEach(function (institution) {
      var place = document.createElement("article");
      place.className = "handoff-institution";
      var name = document.createElement("h3");
      name.textContent = institution.name;
      place.appendChild(name);
      var badge = document.createElement("span");
      badge.className = "handoff-badge";
      badge.textContent = institution.check_level === "verified" ? "전화 확인됨" : "웹 확인";
      place.appendChild(badge);
      var procedure = document.createElement("p");
      procedure.textContent = "이용 절차: " + (institution.referral || "정보 없음");
      place.appendChild(procedure);
      var phone = document.createElement("p");
      phone.textContent = "전화: " + (institution.phone || "정보 없음");
      place.appendChild(phone);
      try {
        var homepage = new URL(institution.homepage);
        if (homepage.protocol === "https:" || homepage.protocol === "http:") {
          var link = document.createElement("a");
          link.textContent = "홈페이지";
          link.href = homepage.href;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          place.appendChild(link);
        }
      } catch (error) { /* An absent / unsafe homepage is never a link. */ }
      card.appendChild(place);
    });
    handoffCardEl = card;
    messagesEl.appendChild(card);
    card.scrollIntoView({ block: "nearest" });
  }

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
    var storedId = localStorage.getItem(PARTICIPANT_KEY);
    if (url.searchParams.has("management_id") || url.searchParams.has("link_ticket")) {
      var managementId = url.searchParams.get("management_id");
      var linkTicket = url.searchParams.get("link_ticket");
      // Keep even incomplete / invalid links for server-side validation, including
      // after a reload. Never turn an unverified URL label into record ownership.
      sessionStorage.setItem(INTAKE_LINK_KEY, JSON.stringify({
        management_id: managementId,
        link_ticket: linkTicket
      }));
      sessionStorage.removeItem(SESSION_KEY);
      sessionStorage.removeItem(SESSION_TOKEN_KEY);
      sessionStorage.removeItem(CONSENT_KEY);
      localStorage.removeItem(PARTICIPANT_KEY);
      localStorage.removeItem(PARTICIPANT_TICKET_KEY);
      sessionStorage.removeItem(DRAFT_KEY);
      sessionStorage.removeItem(PENDING_REQUEST_KEY);
      sessionStorage.removeItem(UI_STATE_KEY);
      storedId = null;
      url.searchParams.delete("management_id");
      url.searchParams.delete("link_ticket");
      window.history.replaceState({}, "", url.pathname + url.search + url.hash);
      if (!MANAGEMENT_ID_PATTERN.test(managementId || "") || !linkTicket) {
        setStatus("링크가 올바르지 않아요. 센터에 다시 요청해 주세요. 긴급 도움: 109 · 1588-9191 · 119");
      }
    }

    if (!storedId) {
      storedId = crypto.randomUUID();
      localStorage.setItem(PARTICIPANT_KEY, storedId);
    }
    return storedId;
  }

  function pendingIntakeLink() {
    try { return JSON.parse(sessionStorage.getItem(INTAKE_LINK_KEY)) || {}; }
    catch (error) { return {}; }
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


  function typeAssistantMessage(text, retryable, requestId) {
    // A completed response must not wait on background-tab animation timers.
    // Retry errors are transient UI feedback, not new conversation turns.
    var rendered;
    if (retryable && retryMessage && retryMessageRequestId === requestId) {
      rendered = retryMessage;
    } else {
      if (retryMessage) retryMessage.row.remove();
      rendered = addMessage("assistant", "");
      retryMessage = retryable ? rendered : null;
      retryMessageRequestId = retryable ? requestId : null;
    }
    appendSupportLinks(rendered.bubble, text);
    rendered.row.scrollIntoView({ block: "nearest" });
    return Promise.resolve(rendered);
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
      progressEl.style.width = Math.min(100, (turn / MAX_TURNS) * 100) + "%";
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
    document.body.setAttribute("data-input-ready", String(Boolean(configReady && (!consentRequired || consentGranted))));
    var length = inputEl.value.length;
    if (characterCountEl) {
      characterCountEl.textContent = length + "/" + MAX_MESSAGE_LEN;
      characterCountEl.classList.toggle("near-limit", length > MAX_MESSAGE_LEN * 0.85);
    }
    sendButtonEl.disabled = requestPending || inputEl.disabled || !inputEl.value.trim();
    if (retryButtonEl) retryButtonEl.disabled = requestPending;
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
      button.className = "reply-suggestion" + (reply.action === "send" ? " reply-suggestion-send" : "");
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
    saveDraft("");
    rememberPending(null);
    sessionStorage.removeItem(UI_STATE_KEY);
    setDeliveryState("ready");
    messagesEl.textContent = "";
    retryMessage = null;
    retryMessageRequestId = null;
    handoffCardEl = null;
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

    var reusableRequest = pendingRequest && pendingRequest.session_id === getSessionId() && pendingRequest.message === message ? pendingRequest : null;
    var request = options.request || reusableRequest || {
      request_id: crypto.randomUUID(),
      message: message,
      session_id: getSessionId()
    };
    var isRetry = options.retry || request === reusableRequest;
    requestPending = true;
    rememberPending(request);
    userHasSpoken = true;
    hideChips();
    hideContextualReplies();
    setStatus("입력 내용을 저장하고 분석하고 있어요…");
    setDeliveryState("analyzing");
    if (!isRetry) addMessage("user", message);
    if (!options.preserveInput) inputEl.value = "";
    saveDraft("");
    inputEl.readOnly = true;
    if (resetSessionEl) resetSessionEl.disabled = true;
    updateInputState();
    showTyping();

    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: request.session_id,
        session_token: getSessionToken() || null,
        participant_id: getParticipantId(),
        participant_ticket: localStorage.getItem(PARTICIPANT_TICKET_KEY) || null,
        message: message,
        request_id: request.request_id,
      }),
    })
      .then(function (response) {
        if (response.ok) return response.json();

        hideTyping();
        return response.json().catch(function () { return {}; }).then(function (error) {
          var detail = error.detail || "처리 결과를 확인하지 못했습니다. 같은 내용으로 다시 시도해 주세요.";
          if (response.status === 401) {
            clearSensitiveTabState();
            disableInput();
            setDeliveryState("ready", "로그인 또는 접수 권한을 다시 확인해 주세요. 이 탭의 임시 내용은 지웠습니다.");
          } else {
            rememberPending(request);
            inputEl.value = message;
            saveDraft(message);
            var conflict = error.code === "request_id_conflict" || /요청.*(다른|충돌)|request.?id/i.test(detail);
            setDeliveryState(conflict ? "confirmation_required" : "retryable", conflict ? "같은 요청 식별자에 다른 내용이 감지되었습니다. 입력을 확인해 주세요." : "전송 결과를 확인하지 못했습니다. 같은 내용으로 다시 시도할 수 있습니다.");
          }
          setStatus(detail);
          requestPending = false;
          inputEl.readOnly = false;
          if (resetSessionEl) resetSessionEl.disabled = false;
          updateInputState();
          return null;
        });
      })
      .then(function (data) {
        if (!data) return;

        hideTyping();
        var retryableResponse = data.processing_status === "retryable" || data.retryable === true;
        if (retryableResponse) {
          rememberPending(request);
          inputEl.value = message;
          saveDraft(message);
        } else {
          rememberPending(null);
        }
        rememberUiState(data);
        rememberCredentials(data);
        deleteSessionEl.hidden = !getSessionToken();
        // fake 모드 진행 접미사(" | 채움: ..")는 패널이 대신 보여주므로 표시에서만 제거.
        var replyText = data.reply.replace(/ \| (채움|다음 질문): .*$/, "");
        setStatus("답변을 작성하고 있어요…");
        typeAssistantMessage(replyText, retryableResponse, request.request_id).then(function () {
          setStatus("");
          setDeliveryState(responseDeliveryState(data));
          updateTurnCounter(data.turn);
          if (data.closing) turnCounterEl.textContent = "마지막 확인";
          if (handoffDelivered(data.handoff)) turnCounterEl.textContent = "전달 완료";
          renderIntake(data.intake);
          if (Array.isArray(data.quick_replies) && data.quick_replies.length) {
            renderServerQuickReplies(data.quick_replies);
          } else {
            renderContextualReplies(data.intake, replyText);
          }
          renderCoachingStatus(data);
          renderHandoff(data.handoff);
          requestPending = false;
          inputEl.readOnly = false;
          if (resetSessionEl) resetSessionEl.disabled = false;

          if (retryableResponse) {
            setStatus("처리 결과를 확정하지 못했습니다. 같은 내용으로 다시 시도해 주세요.");
            updateInputState();
            inputEl.focus();
            return;
          }

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
        rememberPending(request);
        inputEl.value = message;
        saveDraft(message);
        setDeliveryState("retryable");
        setStatus("전송 결과를 확인하지 못했습니다. 입력은 보관되어 있으며 같은 내용으로 다시 시도할 수 있어요.");
        requestPending = false;
        inputEl.readOnly = false;
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
  inputEl.addEventListener("input", function () {
    saveDraft(inputEl.value);
    if (!requestPending && pendingRequest && inputEl.value !== pendingRequest.message) rememberPending(null);
    if (!requestPending) setDeliveryState(inputEl.value ? "draft" : "ready");
  });
  inputEl.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      formEl.requestSubmit();
    }
  });

  if (resetSessionEl) {
    resetSessionEl.addEventListener("click", resetSession);
  }

  if (retryButtonEl) {
    retryButtonEl.addEventListener("click", function () {
      if (!pendingRequest || requestPending) return;
      inputEl.value = pendingRequest.message;
      sendMessage(pendingRequest.message, {request: pendingRequest, retry: true});
    });
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
    setTextIf(".privacy-summary-text", ui.privacy_summary);
    setTextIf(".privacy-body", ui.privacy_body);
    setTextIf(".panel-title", ui.panel_title);
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
    setTextIf(".privacy-summary-text", "학습 대화 안내");
    setTextIf(
      ".privacy-body",
      "대화 내용은 학습 흐름을 이어가기 위해 저장될 수 있습니다. 이름, 연락처, 학교명 같은 개인정보는 입력하지 마세요."
    );
    if (panelEl) panelEl.hidden = true;
    if (stepperEl) stepperEl.hidden = true;
    if (chipsEl) chipsEl.hidden = true;
    intakeSchemaActive = false;
    if (deliveryProgressEl) deliveryProgressEl.hidden = true;
  }

  function applyIntakeMode() {
    greetingText = GREETING;
    document.title = "접수 면담 챗봇";
    setTextIf(".chat-title h1", "접수 면담 챗봇");
    setTextIf(".privacy-summary-text", "첫 상담 전 접수용 안내");
    setTextIf(
      ".privacy-body",
      "대화 내용은 서버에 저장됩니다. 자·타해 위험, 학대 의심, 법적 요청처럼 안전 예외가 있는 경우에는 보호자·전문기관과 공유될 수 있습니다."
    );
    if (deliveryProgressEl) deliveryProgressEl.hidden = false;
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
        if (!response.ok) {
          var error = new Error(data.detail || "처리하지 못했습니다.");
          error.status = response.status;
          throw error;
        }
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
    postJson("/api/consent", Object.assign({
      session_id: getSessionId(), accepted: accepted, consent_version: privacy.consent_version,
      idempotency_key: getSessionId(), session_token: getSessionToken()
    }, pendingIntakeLink())).then(function (data) {
      consentCardEl.hidden = true;
      if (!data.accepted) {
        var refusal = addMessage("assistant", data.reply);
        appendSupportLinks(refusal.bubble, data.reply);
        disableInput();
        return;
      }
      rememberCredentials(data);
      sessionStorage.removeItem(UI_STATE_KEY);
      sessionStorage.removeItem(INTAKE_LINK_KEY);
      sessionStorage.setItem(CONSENT_KEY, privacy.consent_version);
      consentGranted = true;
      setDeliveryState("ready");
      updateInputState();
      deleteCodeValueEl.textContent = data.delete_code;
      deleteCodeCardEl.hidden = false;
      deleteSessionEl.hidden = false;
      inputEl.disabled = false;
      addMessage("assistant", data.reply);
      maybeShowChips();
      inputEl.focus();
    }).catch(function (error) {
      if (error.status === 401) clearSensitiveTabState();
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
      if (error.status === 401) clearSensitiveTabState();
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
      if (!response.ok) {
        var error = new Error("config fetch failed: " + response.status);
        error.status = response.status;
        throw error;
      }
      return response.json();
    })
    .then(function (data) {
      if (data.institution_link_required && !getSessionToken()) {
        return postJson("/api/intake-link/exchange", institutionToken ? {token: institutionToken} : {}).then(function (link) {
          data.privacy.body = "접수 기관: " + link.organization + "\n" + link.purpose + "\n\n" + data.privacy.body;
          institutionToken = null;
          return data;
        }).catch(function (error) {
          error.stage = "intake-link";
          throw error;
        });
      }
      return data;
    })
    .then(function (data) {
      if (data && data.mode === "coaching") applyCoachingMode();
      if (data && data.mode === "intake") applyIntakeMode();
      applyUiConfig(data && data.ui);
      configReady = true;
      consentRequired = data.consent_required === true;
      institutionAccess = data.institution_link_required === true;
      document.getElementById("institution-access-notice").hidden = !institutionAccess;
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
      if (err.status === 401) clearSensitiveTabState();
      configReady = false;
      disableInput();
      hideChips();
      if (err.stage === "intake-link" && err.status === 410) {
        var linkHelp = "센터에서 받은 개별 접수 링크로 열어 주세요. 만료되었거나 이미 사용한 링크라면 담당자에게 새 링크를 요청해 주세요.";
        document.title = "마음 접수 · 링크 확인";
        setTextIf(".chat-title h1", "개별 접수 링크가 필요해요");
        setDeliveryState("link_required", linkHelp);
        setStatus(linkHelp + " 긴급 도움: 109 · 1588-9191 · 119");
      } else {
        setStatus("이용 안내를 불러오지 못했습니다. 새로고침해 주세요. 긴급 도움: 109 · 1588-9191 · 119");
      }
      console.warn("intake config probe failed; stepper stays hidden", err);
    })
    .finally(function () {
      if (configReady && (!consentRequired || consentGranted)) {
        var restored = restoreUiState();
        if (!restored) addMessage("assistant", greetingText);
        applyPendingState();
      }
      updateInputState();
    });

  restorePending();
  updateInputState();
})();
