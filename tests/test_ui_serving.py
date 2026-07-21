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


def _assert_interaction_mode_radios(document: ET.Element) -> None:
    mode_switch = _element_by_id(document, "interaction-mode-switch")
    label_id = mode_switch.attrib.get("aria-labelledby", "")
    radios = [
        element
        for element in mode_switch.iter("input")
        if element.attrib.get("type") == "radio"
    ]
    radio_ids = [radio.attrib.get("id") for radio in radios]
    radio_label_ids = [label.attrib.get("for") for label in mode_switch.iter("label")]

    assert mode_switch.attrib.get("role") == "radiogroup"
    assert "hidden" in mode_switch.attrib
    assert "inert" in mode_switch.attrib
    assert label_id and "".join(_element_by_id(document, label_id).itertext()).strip()
    assert radio_ids == ["interaction-mode-chat", "interaction-mode-voice"]
    assert radio_label_ids == radio_ids
    assert len({radio.attrib.get("name") for radio in radios}) == 1
    assert [radio.attrib.get("id") for radio in radios if "checked" in radio.attrib] == [
        "interaction-mode-chat"
    ]


def _assert_interaction_surfaces(document: ET.Element) -> None:
    parents = {child: parent for parent in document.iter() for child in parent}
    messages = _element_by_id(document, "messages")
    chat_surface = _element_by_id(document, "chat-surface")
    voice_surface = _element_by_id(document, "voice-surface")
    fallback = _element_by_id(document, "voice-text-fallback")

    surfaces_parent = parents[chat_surface]
    assert surfaces_parent is parents[voice_surface], "interaction surfaces must be siblings"
    assert "composer" in surfaces_parent.attrib.get("class", "").split()
    assert messages not in set(chat_surface.iter())
    assert messages not in set(voice_surface.iter())
    assert "hidden" not in chat_surface.attrib
    assert "inert" not in chat_surface.attrib
    assert "hidden" in voice_surface.attrib
    assert "inert" in voice_surface.attrib
    assert all(
        _element_by_id(document, element_id) in set(chat_surface.iter())
        for element_id in ("chat-form", "message-input")
    )
    assert any(
        "composer-meta" in element.attrib.get("class", "").split()
        for element in chat_surface.iter()
    )
    assert all(
        _element_by_id(document, element_id) in set(voice_surface.iter())
        for element_id in (
            "voice-controls",
            "voice-toggle",
            "voice-review",
            "voice-transcript",
            "voice-send",
        )
    )
    assert fallback.tag == "button"
    assert fallback.attrib.get("type") == "button"
    assert "".join(fallback.itertext()).strip() == "채팅 모드로 전환"


def test_root_serves_index_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<html" in response.text.lower()


def test_root_serves_app_js():
    response = client.get("/app.js")
    assert response.status_code == 200
    assert "sendMessage" in response.text


def test_root_serves_hidden_labeled_interaction_mode_radios():
    # Given: the server-rendered application shell.
    response = client.get("/")

    # When: the static DOM contract is parsed.
    document = _parse_index(response.text)

    # Then: one labeled radio group defaults exclusively to Chat.
    _assert_interaction_mode_radios(document)


def test_root_serves_chat_and_voice_as_sibling_surfaces():
    # Given: the server-rendered application shell.
    response = client.get("/")

    # When: the static DOM contract is parsed.
    document = _parse_index(response.text)

    # Then: shared history stays outside the two non-nested interaction surfaces.
    _assert_interaction_surfaces(document)


def test_root_loads_interaction_scripts_in_dependency_order():
    # Given: the server-rendered application shell.
    response = client.get("/")

    # When: script filenames are read in document order.
    document = _parse_index(response.text)
    script_names = [
        Path(element.attrib["src"].split("?", maxsplit=1)[0]).name
        for element in document.iter("script")
        if "src" in element.attrib
    ]

    # Then: each interaction dependency loads before the canonical app shell.
    assert script_names == ["voice.js", "interaction-mode.js", "tts.js", "app.js"]


def test_dual_mode_css_has_accessible_states_and_mobile_overflow_guards():
    # Given: the static stylesheet.
    source = (STATIC_DIR / "style.css").read_text(encoding="utf-8")

    # When: the dual-mode selectors are inspected.
    mobile_source = source[source.index("@media (max-width: 520px)") :]

    # Then: segmented, focus, disabled, error, and 360px-safe rules are present.
    assert ".interaction-mode-options" in source
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in source
    assert ".interaction-mode-option:focus-within" in source
    assert ".interaction-mode-input:checked" in source
    assert ".interaction-mode-input:disabled" in source
    assert all(
        f'[data-voice-state="{state}"]' in source
        for state in ("recording", "review", "ready", "error")
    )
    assert "max-width: 100%;" in source
    assert ".interaction-mode-option" in mobile_source
    assert "min-width: 0;" in mobile_source


def test_interaction_mode_contract_rejects_two_checked_radios():
    # Given: a valid shell mutated to select both radio controls.
    document = _parse_index((STATIC_DIR / "index.html").read_text(encoding="utf-8"))
    voice_radio = _element_by_id(document, "interaction-mode-voice")
    voice_radio.set("checked", "checked")

    # When/Then: the contract identifies the invalid double-selected state.
    with pytest.raises(AssertionError):
        _assert_interaction_mode_radios(document)


def test_interaction_surface_contract_rejects_nested_voice_surface():
    # Given: a valid shell mutated to nest Voice inside Chat.
    document = _parse_index((STATIC_DIR / "index.html").read_text(encoding="utf-8"))
    parents = {child: parent for parent in document.iter() for child in parent}
    chat_surface = _element_by_id(document, "chat-surface")
    voice_surface = _element_by_id(document, "voice-surface")
    parents[voice_surface].remove(voice_surface)
    chat_surface.append(voice_surface)

    # When/Then: the contract identifies the invalid nested state.
    with pytest.raises(AssertionError, match="siblings"):
        _assert_interaction_surfaces(document)


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
