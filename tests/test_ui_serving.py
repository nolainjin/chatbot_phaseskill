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
    assert response.text.index('src="csv.js?v=1"') < response.text.index('src="stats.js?v=6"')
    assert client.get("/csv.js?v=1").status_code == 200


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
