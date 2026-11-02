(function () {
  "use strict";

  var clientListEl = document.getElementById("client-list");
  var emptyClientsEl = document.getElementById("empty-clients");
  var clientCountEl = document.getElementById("client-count");
  var resultDescriptionEl = document.getElementById("result-description");
  var searchFormEl = document.getElementById("client-search-form");
  var searchEl = document.getElementById("client-search");
  var clearSearchEl = document.getElementById("clear-search");
  var exportEl = document.getElementById("export-clients");
  var printEl = document.getElementById("print-clients");
  var statusEl = document.getElementById("stats-status");
  var summaryClientsEl = document.getElementById("summary-clients");
  var summaryRecordsEl = document.getElementById("summary-records");
  var summaryCompleteEl = document.getElementById("summary-complete");
  var tagFiltersEl = document.querySelector(".client-tag-filter");
  var conversationDialogEl = document.getElementById("conversation-dialog");
  var conversationTitleEl = document.getElementById("conversation-title");
  var conversationMetaEl = document.getElementById("conversation-meta");
  var conversationTurnsEl = document.getElementById("conversation-turns");
  var conversationStatusEl = document.getElementById("conversation-status");
  var closeConversationEl = document.getElementById("close-conversation");
  var reviewPendingEl = document.getElementById("review-pending");

  var allRecords = [];
  var visibleRecords = [];
  var activeTag = "all";
  var slotLabels = {};

  function missingLabels(record) {
    return Array.isArray(record.missing) ? record.missing.map(function (id) {
      return slotLabels[id] || id;
    }) : [];
  }

  function text(value, fallback) {
    var normalized = String(value == null ? "" : value).trim();
    return normalized || fallback || "미확인";
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function detailRow(label, value) {
    var row = document.createElement("div");
    row.className = "client-detail-row";
    var term = document.createElement("dt");
    term.textContent = label;
    var description = document.createElement("dd");
    description.textContent = text(value);
    row.append(term, description);
    return row;
  }
  function recordMatchesTag(record) {
    if (activeTag === "all") return true;
    if (activeTag === "summary") return Boolean(record.summary_available);
    if (activeTag === "progress") return !record.summary_available;
    if (activeTag === "위기") return Boolean(record.review_required);
    if (activeTag === "review-pending") return Boolean(record.review_required) && record.review_status === "대기";
    return text(record.track, "미확인") === activeTag;
  }

  function turnLabel(role) {
    if (role === "user") return "내담자";
    if (role === "assistant") return "챗봇";
    return "접수 요약";
  }

  function renderConversation(detail) {
    clear(conversationTurnsEl);
    var turns = Array.isArray(detail.turns) ? detail.turns : [];
    turns.forEach(function (turn) {
      var item = document.createElement("article");
      item.className = "conversation-turn conversation-turn-" + text(turn.role, "summary");
      var label = document.createElement("strong");
      label.textContent = turnLabel(turn.role);
      var body = document.createElement("p");
      body.textContent = text(turn.text, "내용 없음");
      item.append(label, body);
      conversationTurnsEl.appendChild(item);
    });
    conversationStatusEl.textContent = turns.length ? "" : "저장된 대화가 없습니다.";
  }

  async function openConversation(record) {
    conversationTitleEl.textContent = "관리번호 " + text(record.participant_id) + " 대화 내역";
    conversationMetaEl.textContent = text(record.date, "날짜 미확인") + " · 상담자 내부 열람";
    clear(conversationTurnsEl);
    conversationStatusEl.textContent = "대화 내역을 불러오는 중입니다.";
    conversationDialogEl.showModal();
    try {
      var params = new URLSearchParams({
        day: String(record.date || ""),
        session_id: String(record.session_id || "")
      });
      var response = await fetch("/api/stats/session?" + params.toString());
      if (!response.ok) throw new Error("HTTP " + response.status);
      renderConversation(await response.json());
    } catch (error) {
      conversationStatusEl.textContent = "대화 내역을 불러오지 못했습니다.";
    }
  }

  function renderRecord(record) {
    var article = document.createElement("article");
    article.className = "client-record-card";

    var header = document.createElement("header");
    var identity = document.createElement("div");
    var eyebrow = document.createElement("span");
    eyebrow.className = "client-record-date";
    eyebrow.textContent = text(record.date, "날짜 미확인");
    var title = document.createElement("h3");
    title.textContent = "관리번호 " + text(record.participant_id);
    identity.append(eyebrow, title);

    var track = document.createElement("span");
    track.className = "client-track";
    track.textContent = text(record.track, "분류 전");
    header.append(identity, track);

    var complaint = document.createElement("p");
    complaint.className = "client-chief-complaint";
    complaint.textContent = text(record.chief_complaint, "아직 주 호소가 정리되지 않았습니다.");

    var details = document.createElement("dl");
    details.className = "client-record-details";
    details.append(
      detailRow("상황과 영향", record.symptom_context),
      detailRow("현재 대처", record.coping),
      detailRow("주변 도움", record.support),
      detailRow("상담 기대", record.expectation),
      detailRow("추가 확인", missingLabels(record).join(", ") || "없음")
    );

    var footer = document.createElement("footer");
    var summaryState = document.createElement("span");
    summaryState.textContent = record.summary_available
      ? "접수 요약이 준비되었습니다."
      : "접수가 진행 중이거나 요약 전입니다.";
    var conversationButton = document.createElement("button");
    conversationButton.type = "button";
    conversationButton.className = "tool-button conversation-button no-print";
    conversationButton.textContent = "대화 내역 보기";
    conversationButton.addEventListener("click", function () {
      openConversation(record);
    });
    footer.append(summaryState, conversationButton);

    article.append(header, complaint, details, footer);
    if (record.review_required) article.appendChild(renderReview(record));
    return article;
  }

  function renderReview(record) {
    var section = document.createElement("section");
    section.className = "client-review";
    var state = document.createElement("p");
    state.className = "review-state";
    state.textContent = "사람 확인: " + text(record.review_status, "대기");
    var form = document.createElement("form");
    form.className = "review-form no-print";
    var actionLabel = document.createElement("label");
    actionLabel.textContent = "확인 결과";
    var select = document.createElement("select");
    select.required = true;
    var placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "결과 선택";
    select.appendChild(placeholder);
    ["안내 전화함", "기관 연결함", "해당 없음", "연락 불가"].forEach(function (action) {
      var option = document.createElement("option");
      option.value = action;
      option.textContent = action;
      select.appendChild(option);
    });
    actionLabel.appendChild(select);
    var noteLabel = document.createElement("label");
    noteLabel.textContent = "메모 (선택, 200자 이내)";
    var note = document.createElement("textarea");
    note.maxLength = 200;
    note.rows = 2;
    noteLabel.appendChild(note);
    var button = document.createElement("button");
    button.type = "submit";
    button.className = "tool-button";
    button.textContent = "확인 기록 저장";
    var feedback = document.createElement("p");
    feedback.setAttribute("role", "status");
    form.append(actionLabel, noteLabel, button, feedback);
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      button.disabled = true;
      feedback.textContent = "확인 기록을 저장하는 중입니다.";
      try {
        var response = await fetch("/api/review", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ day: record.date, session_id: record.session_id,
            action: select.value, note: note.value })
        });
        if (!response.ok) throw new Error("HTTP " + response.status);
        await loadStats();
      } catch (error) {
        feedback.textContent = "확인 기록을 저장하지 못했습니다. 다시 시도해 주세요.";
      } finally {
        button.disabled = false;
      }
    });
    section.append(state, form);
    return section;
  }

  function renderRecords(records, query) {
    clear(clientListEl);
    visibleRecords = records;
    records.forEach(function (record) {
      clientListEl.appendChild(renderRecord(record));
    });
    emptyClientsEl.hidden = records.length !== 0;
    clientCountEl.textContent = records.length + "건";
    resultDescriptionEl.textContent = query
      ? "관리번호 ‘" + query + "’ 검색 결과입니다."
      : "최근 접수된 내담자부터 표시합니다.";
  }

  function applyFilters() {
    var rawQuery = searchEl.value.trim();
    var query = rawQuery.toLocaleLowerCase("ko-KR");
    var records = allRecords.filter(function (record) {
      var matchesQuery = !query || String(record.participant_id || "")
        .toLocaleLowerCase("ko-KR")
        .includes(query);
      return matchesQuery && recordMatchesTag(record);
    });
    renderRecords(records, rawQuery);
    if (activeTag !== "all") {
      resultDescriptionEl.textContent = "‘" + activeTag + "’ 태그로 분류된 접수 기록입니다.";
    }
  }

  function csvRows(records) {
    var rows = [["관리번호", "접수일", "상담영역", "주호소", "상황과 영향", "현재 대처", "주변 도움", "상담 기대", "추가 확인"]];
    records.forEach(function (record) {
      rows.push([
        record.participant_id,
        record.date,
        record.track,
        record.chief_complaint,
        record.symptom_context,
        record.coping,
        record.support,
        record.expectation,
        missingLabels(record).join(" / ")
      ]);
    });
    return rows;
  }

  function exportCsv() {
    if (!visibleRecords.length) return;
    var csv = csvRows(visibleRecords).map(function (row) {
      return row.map(window.csvCell).join(",");
    }).join("\r\n");
    var blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = "내담자_접수_목록.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function renderSummary(records) {
    var participantIds = new Set(records.map(function (record) {
      return record.participant_id;
    }));
    summaryClientsEl.textContent = participantIds.size.toLocaleString("ko-KR");
    summaryRecordsEl.textContent = records.length.toLocaleString("ko-KR");
    summaryCompleteEl.textContent = records.filter(function (record) {
      return record.summary_available;
    }).length.toLocaleString("ko-KR");
  }


  function isCounselorRecord(record) {
    var participantId = String(record.participant_id || "");
    var sessionId = String(record.session_id || "");
    return Boolean(record.review_required || (participantId && participantId !== sessionId));
  }

  async function loadStats() {
    statusEl.textContent = "내담자 접수 기록을 불러오는 중입니다.";
    try {
      var responses = await Promise.all([
        fetch("/api/stats"),
        fetch("/api/config").then(function (response) {
          return response.ok ? response.json() : {};
        }).catch(function () { return {}; })
      ]);
      var response = responses[0];
      slotLabels = responses[1].slot_labels || {};
      if (!response.ok) throw new Error("HTTP " + response.status);
      var data = await response.json();
      reviewPendingEl.textContent = "위기 확인 대기 " + Number(data.review_pending || 0).toLocaleString("ko-KR") + "건";
      allRecords = Array.isArray(data.recent_sessions)
        ? data.recent_sessions.filter(isCounselorRecord)
        : [];
      applyFilters();
      renderSummary(allRecords);
      statusEl.textContent = data.exists
        ? "내부 접수 기록을 불러왔습니다."
        : "아직 적재된 접수 기록이 없습니다.";
    } catch (error) {
      reviewPendingEl.textContent = "위기 확인 대기 조회 실패";
      statusEl.textContent = "내담자 기록을 불러오지 못했습니다. 관리자 내부 접속 상태를 확인해 주세요.";
    }
  }

  searchFormEl.addEventListener("submit", function (event) {
    event.preventDefault();
    applyFilters();
  });
  searchEl.addEventListener("input", applyFilters);
  clearSearchEl.addEventListener("click", function () {
    searchEl.value = "";
    activeTag = "all";
    tagFiltersEl.querySelectorAll("[data-tag]").forEach(function (button) {
      var selected = button.dataset.tag === "all";
      button.classList.toggle("active", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
    applyFilters();
    searchEl.focus();
  });
  tagFiltersEl.addEventListener("click", function (event) {
    var button = event.target.closest("[data-tag]");
    if (!button) return;
    activeTag = button.dataset.tag;
    tagFiltersEl.querySelectorAll("[data-tag]").forEach(function (candidate) {
      var selected = candidate === button;
      candidate.classList.toggle("active", selected);
      candidate.setAttribute("aria-pressed", String(selected));
    });
    applyFilters();
  });
  closeConversationEl.addEventListener("click", function () {
    conversationDialogEl.close();
  });
  conversationDialogEl.addEventListener("click", function (event) {
    if (event.target === conversationDialogEl) conversationDialogEl.close();
  });
  exportEl.addEventListener("click", exportCsv);
  printEl.addEventListener("click", function () {
    window.print();
  });

  loadStats();
})();
