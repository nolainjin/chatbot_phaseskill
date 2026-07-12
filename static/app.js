// 바닐라 JS 채팅 클라이언트 — 빌드 도구 없음.
(function () {
  "use strict";

  var SESSION_KEY = "lmwiki_session_id";
  var MAX_TURNS = 10;

  var messagesEl = document.getElementById("messages");
  var statusEl = document.getElementById("status");
  var turnCounterEl = document.getElementById("turn-counter");
  var formEl = document.getElementById("chat-form");
  var inputEl = document.getElementById("message-input");
  var sendButtonEl = document.getElementById("send-button");
  var panelEl = document.getElementById("intake-panel");
  var slotListEl = document.getElementById("slot-list");

  function getSessionId() {
    var id = sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }

  function addMessage(role, text) {
    var li = document.createElement("li");
    li.className = "message message-" + role;
    li.textContent = text;
    messagesEl.appendChild(li);
    li.scrollIntoView({ block: "nearest" });
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

  function sendMessage(message) {
    setStatus("");
    addMessage("user", message);
    inputEl.value = "";
    sendButtonEl.disabled = true;
    showTyping();

    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: getSessionId(), message: message }),
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
        addMessage("assistant", data.reply.replace(/ \| (채움|다음 질문): .*$/, ""));
        updateTurnCounter(data.turn);
        renderIntake(data.intake);

        if (data.limit_reached) {
          setStatus("대화 한도에 도달했습니다. 새 세션으로 다시 시작해 주세요.");
          disableInput();
          return;
        }

        sendButtonEl.disabled = false;
        inputEl.focus();
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
})();
