import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
STATIC_DIR = Path(__file__).parents[1] / "static"

# 음성 모드 제거 후 되살아나는 것을 막는 회귀 가드.
# 텍스트 전용 제품이라는 결정을 셸/스타일시트 계약으로 고정한다.
VOICE_MARKERS = ("voice", "tts", "interaction-mode", "마이크", "녹음", "전사")


def _parse_index(source: str) -> ET.Element:
    html_source = (
        source.split("\n", maxsplit=1)[1]
        if source.lower().startswith("<!doctype")
        else source
    )
    xml_source = re.sub(
        r" (?P<name>checked|disabled|hidden|inert|required)(?=[\s>])",
        r' \g<name>=""',
        html_source,
    )
    return ET.fromstring(xml_source)


def _element_by_id(document: ET.Element, element_id: str) -> ET.Element:
    elements = document.findall(f".//*[@id='{element_id}']")
    assert len(elements) == 1, f"expected one #{element_id}, found {len(elements)}"
    return elements[0]


def _assert_chat_surface(document: ET.Element) -> None:
    """텍스트 입력 표면이 composer 안에 있고, 대화 기록은 그 밖에 있어야 한다."""
    parents = {child: parent for parent in document.iter() for child in parent}
    messages = _element_by_id(document, "messages")
    chat_surface = _element_by_id(document, "chat-surface")

    assert "composer" in parents[chat_surface].attrib.get("class", "").split()
    assert messages not in set(chat_surface.iter()), "history must live outside the composer"
    assert "hidden" not in chat_surface.attrib
    assert "inert" not in chat_surface.attrib
    assert all(
        _element_by_id(document, element_id) in set(chat_surface.iter())
        for element_id in ("chat-form", "message-input", "send-button")
    )
    assert any(
        "composer-meta" in element.attrib.get("class", "").split()
        for element in chat_surface.iter()
    )


def test_root_serves_index_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<html" in response.text.lower()


def test_root_serves_app_js():
    response = client.get("/app.js")
    assert response.status_code == 200
    assert "sendMessage" in response.text


def test_root_serves_chat_surface_inside_composer():
    # Given: the server-rendered application shell.
    response = client.get("/")

    # When: the static DOM contract is parsed.
    document = _parse_index(response.text)

    # Then: a single text composer owns the input controls.
    _assert_chat_surface(document)


def test_root_loads_only_the_app_shell_script():
    # Given: the server-rendered application shell.
    response = client.get("/")

    # When: script filenames are read in document order.
    document = _parse_index(response.text)
    script_names = [
        Path(element.attrib["src"].split("?", maxsplit=1)[0]).name
        for element in document.iter("script")
        if "src" in element.attrib
    ]

    # Then: no voice/tts/interaction-mode bundles remain.
    assert script_names == ["app.js"]


@pytest.mark.parametrize("filename", ["index.html", "app.js", "style.css"])
def test_static_shell_is_free_of_voice_markers(filename: str):
    """음성 모드는 제품에서 제거됐다 — 셸 자산에 흔적이 남으면 실패한다."""
    source = (STATIC_DIR / filename).read_text(encoding="utf-8").lower()

    found = [marker for marker in VOICE_MARKERS if marker in source]

    assert not found, f"{filename}에 음성 잔재가 남아 있습니다: {found}"


def test_voice_assets_are_not_served():
    """삭제된 음성 번들은 404여야 한다 (정적 마운트에 남아 있으면 실패)."""
    for path in ("/voice.js", "/tts.js", "/interaction-mode.js"):
        assert client.get(path).status_code == 404, f"{path}가 아직 서빙되고 있습니다"


def test_chat_surface_contract_rejects_history_inside_composer():
    # Given: a valid shell mutated to nest the history inside the composer.
    document = _parse_index((STATIC_DIR / "index.html").read_text(encoding="utf-8"))
    parents = {child: parent for parent in document.iter() for child in parent}
    messages = _element_by_id(document, "messages")
    chat_surface = _element_by_id(document, "chat-surface")
    parents[messages].remove(messages)
    chat_surface.append(messages)

    # When/Then: the contract identifies the invalid nested state.
    with pytest.raises(AssertionError, match="history must live outside"):
        _assert_chat_surface(document)


def test_composer_css_keeps_mobile_overflow_guards():
    # Given: the static stylesheet.
    source = (STATIC_DIR / "style.css").read_text(encoding="utf-8")

    # When: the mobile breakpoint is inspected.
    mobile_source = source[source.index("@media (max-width: 520px)") :]

    # Then: 360px-safe rules survive the voice removal.
    assert ".composer" in source
    assert "max-width: 100%;" in source
    assert "min-width: 0;" in mobile_source


def test_stats_serves_csv_formula_neutralizer_before_dashboard_script():
    response = client.get("/stats.html")

    assert response.status_code == 200
    assert response.text.index('src="csv.js?v=1"') < response.text.index('src="stats.js?v=8"')
    assert client.get("/csv.js?v=1").status_code == 200


def test_stats_dashboard_is_counselor_first_without_triage_tabs():
    response = client.get("/stats.html")

    assert response.status_code == 200
    assert "최근 내담자" in response.text
    assert "내담자 관리번호 찾기" in response.text
    assert "CSV 내보내기" in response.text
    assert "인쇄하기" in response.text
    assert "관리 대상" not in response.text
    assert "위기 우선" not in response.text
    assert "위기만 보기" in response.text
    assert "요약 완료" in response.text
    assert 'id="conversation-dialog"' in response.text
    stats_script = client.get("/stats.js?v=8")
    assert stats_script.status_code == 200
    assert "/api/stats/session?" in stats_script.text
    assert "대화 내역 보기" in stats_script.text


def test_public_chat_page_has_no_stats_navigation():
    response = client.get("/")

    assert response.status_code == 200
    assert "stats.html" not in response.text
    assert "내담자 통계 보기" not in response.text

def test_chat_client_supports_management_number_links():
    response = client.get("/app.js?v=19")

    assert response.status_code == 200
    assert 'url.searchParams.get("management_id")' in response.text
    assert "MANAGEMENT_ID_PATTERN" in response.text
    assert "window.history.replaceState" in response.text


def test_chat_client_linkifies_verified_support_resources():
    response = client.get("/app.js?v=19")

    assert response.status_code == 200
    assert '"109": "tel:109"' in response.text
    assert '"119": "tel:119"' in response.text
    assert 'link.rel = "noopener noreferrer"' in response.text
    assert "appendSupportLinks(rendered.bubble, text)" in response.text


def test_intake_ui_preserves_drafts_and_retries_the_same_request():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert 'id="delivery-status"' in html
    assert '같은 내용 다시 전송' not in html
    assert 'id="retry-button"' not in html
    assert 'request_id: request.request_id' in script
    assert 'sessionStorage.setItem(PENDING_REQUEST_KEY' in script
    assert 'sessionStorage.setItem(UI_STATE_KEY' in script
    assert 'function restoreUiState()' in script
    assert 'localStorage.setItem(PENDING_REQUEST_KEY' not in script
    assert 'coach_stage: data.coach_stage' not in script
    assert 'session_token: data.session_token' not in script
    assert 'participant_ticket: data.participant_ticket' not in script
    assert 'role="status" aria-live="polite" aria-atomic="true"' in html
    assert 'pendingRequest.message === message ? pendingRequest : null' in script
    assert 'data.processing_status === "retryable" || data.retryable === true' in script
    assert 'rememberPending(request);' in script
    assert 'function clearSensitiveTabState()' in script
    assert 'response.status === 401' in script
    assert 'applyPendingState();' in script
    assert 'messagesEl.textContent = "";' in script
    assert 'deleteCodeCardEl.hidden = true;' in script
    assert 'deleteCodeValueEl.textContent = "";' in script
    assert 'data.handoff.mode === "center")) return "delivered"' not in script
    assert script.count('if (handoffDelivered(data.handoff)) turnCounterEl.textContent = "전달 완료";') == 2
    assert 'retryButtonEl' not in script
    assert 'options.retry' not in script
    assert '접수 완료로 표시되었습니다. 상담사 검토 완료를 뜻하지는 않습니다.' in script
    assert '접수 중에도 소속 센터의 권한 있는 담당자가 확인할 수 있어요.' in script
    assert '아직 센터 전달 전입니다.' not in script
    assert 'id="institution-access-notice" hidden' in html
    assert '아직 보내지 않은 입력은 이 탭에만 임시 보관됩니다.' in html


def test_portal_separates_intake_review_and_evidence_states():
    html = (STATIC_DIR / "portal" / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "portal" / "app.js").read_text(encoding="utf-8")

    assert html.index('id="layout"') < html.index('id="link-panel"') < html.index('id="registration-panel"')
    assert "접수 링크 발급 및 관리" in html
    assert 'const intakeStatus' in script
    assert 'const reviewStatus' in script
    assert 'declined:"답변하지 않음"' in script
    assert 'not_applicable:"해당 없음"' in script
    assert 'confirmed:"내담자 진술",answered:"내담자 진술",unclear:"추가 확인 필요"' in script
    assert 'state==="unconfirmed"&&value!=="미확인"?"answered":state' not in script
    assert 'Object.prototype.hasOwnProperty.call(evidence,key)||Boolean(slots[key])' in script
    assert 'Array.isArray(reportRepairs)&&reportRepairs.length' in script
    assert 'const value=state==="unconfirmed"?"미확인"' in script
    assert 'const coreKeys=visibleKeys.filter' in script
    assert 'detailSection.append(el("h3","세부 항목"))' in script
    assert 'r.sources["center_request:"+index]' in script
    assert '"원문 출처 #"+source.seq' in script


def test_csv_cell_neutralizes_formula_markers():
    source = (Path(__file__).parents[1] / "static" / "csv.js").read_text(encoding="utf-8")
    script = (
        "const vm=require('node:vm');"
        "const context={window:{}};"
        f"vm.runInNewContext({json.dumps(source)}, context);"
        "console.log(JSON.stringify(['=1','+1','-1','@x','normal'].map(context.window.csvCell)));"
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    cells = json.loads(result.stdout)

    assert cells == ['"\'=1"', '"\'+1"', '"\'-1"', '"\'@x"', '"normal"']
