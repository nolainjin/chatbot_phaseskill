"""C5: local-only synthetic matching, terminal handoff and browser behavior."""

import hashlib
import json
import logging
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app import chat, intake, main, referral
from app.config import Settings
from app.knowledge_pack import validate_pack

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "knowledge-maeum"
FIXTURE = ROOT / "tests/fixtures/maeum_map_fixture.yaml"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(chat, "_sessions", {})
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("KNOWLEDGE_DIR", str(PACK))
    monkeypatch.delenv("REFERRAL_MIN_CHECK", raising=False)


@pytest.fixture
def institutions():
    return referral.load_map(FIXTURE)


def _summary(**values):
    return {"slots": {"track": "정서", "area": "수성구", "age_band": "20대", **values}}


def _ids(result):
    return [item["id"] for item in result["institutions"]]


def test_local_then_age_then_check_then_id_order(institutions):
    result = referral.match(_summary(), institutions)
    assert _ids(result) == ["suseong-youth", "suseong-general", "city-youth"]
    assert not result["fallback_used"]
    assert all(item["check_level"] == "verified" for item in result["institutions"])
    assert result == referral.match(_summary(), list(reversed(institutions)))


@pytest.mark.parametrize("area", ["대구 밖", "미확인", "말하지 않음", None, "부산"])
def test_outside_or_unknown_area_only_matches_city(area, institutions):
    assert _ids(referral.match(_summary(area=area), institutions)) == ["city-youth", "city-general"]


@pytest.mark.parametrize("age_band", ["미확인", "말하지 않음", None])
def test_unknown_age_excludes_all_age_limits(age_band, institutions):
    assert _ids(referral.match(_summary(age_band=age_band), institutions)) == ["suseong-general", "city-general"]


def test_check_threshold_and_unconfirmed_exclusion(institutions):
    web = next(item for item in institutions if item["id"] == "suseong-web")
    assert referral.match(_summary(), [web])["fallback_used"]
    result = referral.match(_summary(), institutions, "web")
    assert _ids(result) == ["suseong-youth", "suseong-web", "suseong-general"]
    assert result["institutions"][1]["check_level"] == "web"
    assert "unconfirmed" not in _ids(result)
    # Tie-breaking by id is stable even if the map is rearranged.
    clone = {**web, "id": "aaa-web"}
    assert _ids(referral.match(_summary(), [web, clone], "web")) == ["aaa-web", "suseong-web"]


def test_inclusive_age_overlap_and_unknown_track(institutions):
    youth = next(item for item in institutions if item["id"] == "suseong-youth")
    assert _ids(referral.match(_summary(age_band="10대", track="미확인"), [youth])) == [youth["id"]]
    assert referral.match(_summary(age_band="40대"), [youth])["fallback_used"]
    elderly = {**youth, "age_min": 65, "age_max": None}
    assert _ids(referral.match(_summary(age_band="60대 이상"), [elderly])) == [youth["id"]]
    assert referral.match(_summary(track="중독"), institutions)["fallback_used"]


def test_note_is_five_fixed_lines_and_preserves_the_users_words():
    schema = intake.load_schema(PACK)
    summary = _summary(chief_complaint="불안해서 힘들어요", symptom_context="두 달 전부터 잠을 설쳐요",
                       coping="미확인", expectation="마음을 정리하고 싶어요", contact_pref="전화")
    assert referral.build_handoff_note(summary, schema) == [
        "지금 힘든 일: 불안해서 힘들어요", "시작 시기와 일상 영향: 두 달 전부터 잠을 설쳐요",
        "해본 대처: 말하지 않음", "바라는 도움: 마음을 정리하고 싶어요", "연결 선호(연결 방식): 전화",
    ]
    empty_note = referral.build_handoff_note({}, schema)
    assert len(empty_note) == 5 and all(line.endswith(": 말하지 않음") for line in empty_note)
    assert not any(word in "\n".join(empty_note) for word in ("진단", "장애", "판단", "추정"))
    relationship = _summary(track="관계", relationship_duration="지난달부터 잠이 안 와요",
                            symptom_context="이전 트랙 값")
    assert referral.build_handoff_note(relationship, schema)[1].endswith("지난달부터 잠이 안 와요")


def _finish(settings=None, session_id="synthetic-referral"):
    settings = settings or Settings.from_env()
    replies = []
    for message in ("우울해서 잠을 못 자요", "두 달 전부터 일상에서 집중이 어려워요", "산책을 해봤어요",
                    "친구에게 말했어요", "도움을 받을 방법을 알고 싶어요", "수성구", "20대", "전화"):
        replies.append(chat.handle_message(session_id, message, settings))
    assert all("handoff" not in reply for reply in replies[:-1])
    assert replies[-1]["conversation_ended"] is True
    return replies[-1]


def _saved(tmp_path, session_id="synthetic-referral"):
    return json.loads(next((tmp_path / "data/conversations").glob(f"*/{session_id}.json")).read_text())


def test_real_empty_map_is_loaded_and_gap_is_logged_once(caplog, tmp_path):
    assert referral.load_map(PACK / referral.MAP_FILENAME) == []
    with caplog.at_level(logging.WARNING):
        result = _finish()
        session = chat._sessions["synthetic-referral"]
        # Follow-up calls must not duplicate the gap record for this session.
        for _ in range(chat.MAX_TURNS - session.turns + 1):
            last = chat.handle_message(session.session_id, "고맙습니다", Settings.from_env())
    handoff = result["handoff"]
    assert handoff["map_status"] == "loaded" and handoff["fallback_used"]
    assert handoff["institutions"] == [] and len(handoff["note"]) == 5
    assert all(number in result["reply"] for number in ("1577-0199", "109"))
    gaps = [record.message for record in caplog.records if "map_gap" in record.message]
    assert len(gaps) == 1
    assert session.session_id not in gaps[0]
    assert hashlib.sha256(session.session_id.encode()).hexdigest() in gaps[0]
    assert last["limit_reached"] and last["handoff"] == handoff
    saved = _saved(tmp_path)
    assert saved["intake_snapshot"]["referral"] == {
        "institution_ids": [], "fallback_used": True, "map_status": "loaded",
    }
    terminal_summary = json.loads(next(t["text"] for t in saved["turns"] if t["role"] == "intake_summary"))
    assert terminal_summary["referral"]["fallback_used"] is True


def test_matching_exit_and_metadata_use_fixture_ids(tmp_path):
    pack = tmp_path / "pack"
    shutil.copytree(PACK, pack)
    shutil.copyfile(FIXTURE, pack / referral.MAP_FILENAME)
    settings = replace(Settings.from_env(), knowledge_dir=str(pack))
    result = _finish(settings)
    assert not result["handoff"]["fallback_used"]
    assert _ids(result["handoff"]) == ["suseong-youth", "suseong-general", "city-youth"]
    assert _saved(tmp_path)["intake_snapshot"]["referral"]["institution_ids"] == _ids(result["handoff"])


def test_missing_map_and_turn_limit_with_unfilled_slots(tmp_path, caplog):
    pack = tmp_path / "missing-map-pack"
    pack.mkdir()
    shutil.copyfile(PACK / "_intake_schema.md", pack / "_intake_schema.md")
    settings = replace(Settings.from_env(), knowledge_dir=str(pack))
    with caplog.at_level(logging.WARNING):
        for _ in range(chat.MAX_TURNS):
            result = chat.handle_message("synthetic-limited", "안녕하세요", settings)
    assert result["turn"] == chat.MAX_TURNS and result["intake"]["unfilled"]
    assert result["handoff"]["map_status"] == "missing"
    assert result["handoff"]["fallback_used"]
    assert "map_gap" in caplog.text
    assert referral.load_map(pack / referral.MAP_FILENAME) is None


def test_real_model_cannot_rewrite_handoff(monkeypatch, tmp_path):
    calls = []
    def model(**kwargs):
        calls.append(kwargs)
        return "모델이 쓴 다른 정리문입니다."
    monkeypatch.setattr(chat.llm, "ask", model)
    result = _finish(replace(Settings.from_env(), model="synthetic-model"))
    assert len(calls) == 8  # No second model call to summarize / match.
    assert result["handoff"]["note"][0] == "지금 힘든 일: 우울해서 잠을 못 자요"
    assert "모델이 쓴" not in "\n".join(result["handoff"]["note"])


def test_handoff_redacts_direct_identifiers(monkeypatch):
    schema = intake.load_schema(PACK)
    session = chat._get_session("synthetic-redaction")
    session.slots = {"track": "정서", "chief_complaint": "연락은 010-1234-5678, synthetic@example.invalid"}
    result = chat._build_handoff(session, schema, Settings.from_env())
    assert "010-1234-5678" not in result["note"][0]
    assert "synthetic@example.invalid" not in result["note"][0]
    assert "[redacted-phone]" in result["note"][0]


def test_crisis_completion_preserves_safety_and_has_no_handoff():
    settings = Settings.from_env()
    result = chat.handle_message("synthetic-crisis-exit", "죽고 싶어요", settings)
    assert "handoff" not in result
    assert "109" in result["reply"] and "119" in result["reply"]
    for message in ("도움을 받고 싶어요", "아니요"):
        result = chat.handle_message("synthetic-crisis-exit", message, settings)
        assert "handoff" not in result
    assert result["conversation_ended"]
    assert "바로 전화해 주세요" in result["reply"] and "현재 안전이 걱정되는 상황" in result["reply"]


def test_addiction_keeps_its_existing_specialist_path():
    result = chat.handle_message("synthetic-addiction-exit", "술을 못 끊겠어요", Settings.from_env())
    assert "handoff" not in result
    assert "중독관리" in result["reply"]


def test_red_flags_block_the_exit_even_without_crisis_track(monkeypatch):
    schema = intake.load_schema(PACK)
    flagged = replace(schema, slots=[replace(slot, red_flag=True) if slot.id == "chief_complaint" else slot for slot in schema.slots])
    monkeypatch.setattr(intake, "load_schema", lambda _: flagged)
    session = chat._get_session("synthetic-red-flag")
    session.turns = chat.MAX_TURNS - 1
    result = chat.handle_message(session.session_id, "우울해요", Settings.from_env())
    assert "handoff" not in result
    assert "109" in result["reply"] and "119" in result["reply"]


@pytest.mark.parametrize("field,value", [
    ("kind", "잘못된 종류"), ("area", "부산"), ("tracks", ["기타"]), ("tracks", "정서"),
    ("web_checked_at", "2026/10/01"), ("verified_at", "2026-02-30"),
    ("verified_at", "2026-10-01T12:00:00"), ("age_min", True), ("age_min", -1),
    ("age_max", 18), ("phone", 123), ("services", {}), ("homepage", "javascript:alert(1)"),
])
def test_invalid_map_fields_raise(tmp_path, institutions, field, value):
    path = tmp_path / referral.MAP_FILENAME
    path.write_text(yaml.safe_dump({"institutions": [{**institutions[0], field: value}]}), encoding="utf-8")
    with pytest.raises(referral.MapValidationError):
        referral.load_map(path)


@pytest.mark.parametrize("content", ["", "institutions: {}", "institutions: [null]", "institutions: [{id: missing}]",
                                     "institutions: []\ninstitutions: []"])
def test_invalid_map_shape_raises(tmp_path, content):
    path = tmp_path / referral.MAP_FILENAME
    path.write_text(content, encoding="utf-8")
    with pytest.raises(referral.MapValidationError):
        referral.load_map(path)


def test_invalid_kind_fails_validator_and_startup(tmp_path, institutions, monkeypatch):
    pack = tmp_path / "invalid-pack"
    shutil.copytree(PACK, pack)
    path = pack / referral.MAP_FILENAME
    path.write_text(yaml.safe_dump({"institutions": [{**institutions[0], "kind": "오류"}]}), encoding="utf-8")
    assert not validate_pack(pack).valid
    process = subprocess.run([sys.executable, str(ROOT / "scripts/validate_knowledge_pack.py"), str(pack)],
                             capture_output=True, text=True)
    assert process.returncode == 1 and "REFERRAL_MAP_INVALID" in process.stdout
    monkeypatch.setenv("KNOWLEDGE_DIR", str(pack))
    with pytest.raises(referral.MapValidationError), TestClient(main.app):
        pass


def test_min_check_config_validation(monkeypatch):
    assert Settings.from_env().referral_min_check == "verified"
    monkeypatch.setenv("REFERRAL_MIN_CHECK", "web")
    assert Settings.from_env().referral_min_check == "web"
    monkeypatch.setenv("REFERRAL_MIN_CHECK", "anything")
    with pytest.raises(ValueError), TestClient(main.app):
        pass


def test_api_config_exposes_schema_labels():
    with TestClient(main.app) as client:
        labels = client.get("/api/config").json()["slot_labels"]
    assert {key: labels[key] for key in ("area", "age_band", "contact_pref")} == {
        "area": "거주 구·군", "age_band": "연령대", "contact_pref": "연결 방식",
    }


def test_api_consent_to_terminal_handoff(tmp_path):
    with TestClient(main.app) as client:
        config = client.get("/api/config").json()
        response = client.post("/api/consent", json={"session_id": "synthetic-api-referral",
            "accepted": True, "consent_version": config["privacy"]["consent_version"]})
        assert response.status_code == 200
        token = response.json()["session_token"]
        for message in ("우울해서 잠을 못 자요", "두 달 전부터 집중이 어려워요", "산책을 해봤어요",
                        "친구에게 말했어요", "도움을 받고 싶어요", "수성구", "20대", "전화"):
            response = client.post("/api/chat", json={"session_id": "synthetic-api-referral",
                "session_token": token, "message": message})
            assert response.status_code == 200
        assert response.json()["handoff"]["map_status"] == "loaded"
        assert response.json()["handoff"]["fallback_used"]


_BROWSER_SCRIPT = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const spec = JSON.parse(fs.readFileSync(0, 'utf8'));
class Node {
  constructor(tag = '') {
    this.tag = tag; this.hidden = true; this.disabled = false; this.value = '';
    this.children = []; this.listeners = {}; this.style = {}; this._text = '';
    this.scrollHeight = 30; this.classList = {toggle() {}};
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(n => n.textContent).join(''); }
  set innerHTML(value) { assert.ok(value.startsWith('<svg '), 'dynamic HTML is forbidden'); }
  appendChild(node) { node.parent = this; this.children.push(node); return node; }
  append(...nodes) { nodes.forEach(n => this.appendChild(n)); }
  removeChild(node) { this.children = this.children.filter(n => n !== node); }
  get firstChild() { return this.children[0]; }
  remove() { if (this.parent) this.parent.removeChild(this); }
  setAttribute(key, value) { this[key] = value; }
  querySelectorAll() { return []; }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  scrollIntoView() {}
  focus() {}
  click() { clicks.push(this); if (this.listeners.click) return this.fire('click'); }
  fire(name) { return this.listeners[name]({preventDefault() {}}); }
}
const nodes = new Map();
const node = id => { if (!nodes.has(id)) nodes.set(id, new Node()); return nodes.get(id); };
const storage = () => ({data: {}, getItem(k) {return this.data[k] || null;},
  setItem(k,v) {this.data[k] = v;}, removeItem(k) {delete this.data[k];}});
const copies = [], downloads = [], clicks = [], requests = [];
class LocalURL extends URL {}
LocalURL.createObjectURL = blob => {downloads.push(blob); return 'blob:synthetic';};
LocalURL.revokeObjectURL = () => {};
const config = {intake_schema: true, mode: 'intake', ui: {}, slot_labels: spec.labels};
const context = {
  document: {getElementById: node, querySelector: node, querySelectorAll() {return [];},
    createElement(tag) {return new Node(tag);}, body: new Node('body'),
    createTextNode(text) {const n = new Node(); n.textContent = text; return n;}},
  window: {location: {href: 'http://test.local/'}, history: {replaceState() {}},
    matchMedia() {return {matches: true};}, setTimeout(f) {f();}, csvCell(v) {return String(v);}},
  navigator: {clipboard: {writeText(text) {copies.push(text); return Promise.resolve();}}},
  localStorage: storage(), sessionStorage: storage(), URL: LocalURL, URLSearchParams, Blob,
  crypto: {randomUUID() {return 'synthetic-ui';}}, console: {warn() {}},
  fetch(url, options) {
    requests.push(url);
    let data = url === '/api/config' ? config : spec.response;
    return Promise.resolve({ok: true, json() {return Promise.resolve(data);}});
  }
};
const tick = async () => {for (let i=0; i<8; i++) await new Promise(setImmediate);};
const walk = node => [node, ...node.children.flatMap(walk)];
(async () => {
  vm.runInNewContext(spec.source, context);
  await tick();
  if (spec.mode === 'stats') {
    const display = node('client-list').textContent;
    Object.values(spec.labels).forEach(label => assert.ok(display.includes(label)));
    assert.ok(!display.includes('age_band'));
    node('export-clients').fire('click');
    const csv = await downloads[0].text();
    Object.values(spec.labels).forEach(label => assert.ok(csv.includes(label)));
    assert.ok(!csv.includes('contact_pref'));
    return;
  }
  node('message-input').value = '합성 입력';
  node('chat-form').fire('submit');
  await tick();
  const cards = node('messages').children.filter(n => n.className === 'handoff-card');
  assert.equal(cards.length, 1);
  const card = cards[0];
  assert.ok(card.textContent.includes('기관에 전할 정리'));
  assert.ok(card.textContent.includes('연결할 수 있는 곳'));
  assert.ok(card.textContent.includes('<script>합성 텍스트</script>'));
  assert.equal(node('message-input').disabled, true);
  let buttons = walk(card).filter(n => n.tag === 'button');
  await buttons.find(n => n.textContent === '정리문 복사').fire('click');
  assert.equal(copies[0], spec.response.handoff.note.join('\n'));
  buttons.find(n => n.textContent === '.txt 내려받기').fire('click');
  assert.equal(await downloads[0].text(), copies[0] + '\n');
  assert.equal(clicks[0].download, '기관에-전할-정리.txt');
  if (spec.response.handoff.fallback_used) {
    assert.ok(card.textContent.includes('가까운 기관을 아직 정리하지 못했어요'));
    assert.ok(card.textContent.includes('1577-0199') && card.textContent.includes('109'));
  } else {
    const links = walk(card).filter(n => n.tag === 'a');
    assert.equal(links.length, 1); // A second institution has a javascript: URL.
    assert.equal(links[0].rel, 'noopener noreferrer');
    assert.equal(links[0].target, '_blank');
    assert.ok(card.textContent.includes('전화 확인됨') && card.textContent.includes('웹 확인'));
    assert.ok(card.textContent.includes('<img src=x>'));
  }
  node('reset-session').fire('click');
  assert.equal(node('messages').children.filter(n => n.className === 'handoff-card').length, 0);
  assert.equal(node('message-input').disabled, false);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""


@pytest.mark.parametrize("fallback", [False, True])
def test_real_ui_script_renders_text_safely_copies_downloads_and_resets(fallback):
    note = referral.build_handoff_note(_summary(chief_complaint="<script>합성 텍스트</script>"), intake.load_schema(PACK))
    places = [
        {"name": "가상 <img src=x>센터", "referral": "가상 예약", "phone": "000-0000-0000",
         "homepage": "https://synthetic.example.invalid", "check_level": "verified"},
        {"name": "가상 웹센터", "referral": "가상 문의", "phone": "000-0000-0000",
         "homepage": "javascript:alert(1)", "check_level": "web"},
    ]
    response = {"reply": "합성 종료", "turn": 8, "conversation_ended": True,
                "handoff": {"note": note, "institutions": [] if fallback else places, "fallback_used": fallback}}
    _run_browser("app.js", response, "chat")


def _run_browser(filename, response, mode):
    payload = {"source": (ROOT / "static" / filename).read_text(), "response": response, "mode": mode,
               "labels": {"area": "거주 구·군", "age_band": "연령대", "contact_pref": "연결 방식"}}
    process = subprocess.run(["node", "-e", _BROWSER_SCRIPT], input=json.dumps(payload), text=True, capture_output=True)
    assert process.returncode == 0, process.stdout + process.stderr


def test_real_stats_script_uses_schema_labels_in_display_and_csv():
    response = {"exists": True, "recent_sessions": [{"session_id": "synthetic-session", "participant_id": "p_synthetic",
                 "missing": ["area", "age_band", "contact_pref"]}]}
    _run_browser("stats.js", response, "stats")
