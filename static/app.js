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

  function updateTurnCounter(turn) {
    turnCounterEl.textContent = turn + "/" + MAX_TURNS;
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

    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: getSessionId(), message: message }),
    })
      .then(function (response) {
        if (response.ok) return response.json();

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

        addMessage("assistant", data.reply);
        updateTurnCounter(data.turn);

        if (data.limit_reached) {
          setStatus("대화 한도에 도달했습니다. 새 세션으로 다시 시작해 주세요.");
          disableInput();
          return;
        }

        sendButtonEl.disabled = false;
        inputEl.focus();
      })
      .catch(function () {
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
