"""Consent at the HTTP boundary; all records and model work stay synthetic/local."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import chat, consent, main, ratelimit

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "knowledge-maeum"
VERSION = "maeum-2026-11-02"


@pytest.fixture
def consent_client(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MODEL", "fake")
    monkeypatch.setenv("KNOWLEDGE_DIR", str(PACK))
    monkeypatch.setenv("RETENTION_RAW_DAYS", "90")
    monkeypatch.setenv("RETENTION_SUMMARY_DAYS", "365")
    monkeypatch.setattr(chat, "_sessions", {})
    monkeypatch.setattr(main, "_rate_limiter", ratelimit.RateLimiter())
    with TestClient(main.app) as client:
        yield client


def test_chat_before_consent_is_409_with_all_safety_numbers(consent_client):
    response = consent_client.post("/api/chat", json={"session_id": "unconsented", "message": "죽고 싶어요"})
    assert response.status_code == 409
    assert main._PUBLIC_TERMINAL_SAFETY_NOTICE in response.json()["detail"]
    assert not chat._sessions
    assert not list(Path("data/conversations").glob("*/*.json"))


def test_refusal_saves_nothing_and_returns_safety_numbers(consent_client):
    response = consent_client.post("/api/consent", json={"session_id": "refusal", "accepted": False, "consent_version": VERSION})
    assert response.status_code == 200
    assert response.json()["accepted"] is False
    for number in ("109", "1588-9191", "119"):
        assert number in response.json()["reply"]
    assert not list(Path(".").rglob("data/*"))
    assert not chat._sessions


def test_acceptance_metadata_survives_chat_and_issues_owned_session(consent_client):
    response = consent_client.post("/api/consent", json={"session_id": "accepted", "accepted": True, "consent_version": VERSION})
    assert response.status_code == 200
    result = response.json()
    assert all(result[k] for k in ("session_token", "participant_id", "participant_ticket", "delete_code", "greeting", "opening_question"))
    assert result["turn"] == 0
    assert main._verify_participant_ticket(result["participant_id"], result["participant_ticket"])
    assert chat._sessions["accepted"].consent_version == VERSION
    for message in ("우울해서 잠을 못 자요", "두 달 전부터 집중하기 어려워요"):
        reply = consent_client.post("/api/chat", json={"session_id": "accepted", "session_token": result["session_token"], "message": message})
        assert reply.status_code == 200
    payload = json.loads(next(Path("data/conversations").glob("*/accepted.json")).read_text())
    assert payload["consent_version"] == VERSION
    assert payload["consented_at"] == chat._sessions["accepted"].consented_at
    assert len(payload["turns"]) == 4
    unauthorized = consent_client.post("/api/chat", json={"session_id": "accepted", "message": "계속"})
    assert unauthorized.status_code == 401
    duplicate = consent_client.post("/api/consent", json={"session_id": "accepted", "accepted": True, "consent_version": VERSION})
    assert duplicate.status_code == 409


def test_consent_metadata_follows_session_across_midnight(consent_client, monkeypatch):
    from datetime import date, timedelta
    from app import storage

    result = consent_client.post("/api/consent", json={"session_id": "midnight", "accepted": True, "consent_version": VERSION}).json()
    original = chat._sessions["midnight"].consented_at
    tomorrow = date.today() + timedelta(days=1)

    class Tomorrow(date):
        @classmethod
        def today(cls):
            return tomorrow

    monkeypatch.setattr(storage, "date", Tomorrow)
    response = consent_client.post("/api/chat", json={"session_id": "midnight", "session_token": result["session_token"], "message": "우울해요"})
    assert response.status_code == 200
    paths = list(Path("data/conversations").glob("*/midnight.json"))
    assert len(paths) == 2
    for path in paths:
        payload = json.loads(path.read_text())
        assert payload["consented_at"] == original
        assert payload["consent_version"] == VERSION


def test_wrong_version_is_409_without_records(consent_client):
    response = consent_client.post("/api/consent", json={"session_id": "wrong-version", "accepted": True, "consent_version": "old"})
    assert response.status_code == 409
    assert not Path("data").exists()


def test_config_has_pack_owned_notice_and_ui(consent_client):
    config = consent_client.get("/api/config").json()
    assert config["consent_required"] is True
    assert config["privacy"] == consent.load_privacy(PACK).as_dict()
    assert config["ui"]["title"] == "마음 이야기 입구"
    assert config["opening_question"] in "요즘 마음에 걸리는 일이 있다면 편하게 말씀해 주실래요?"


def test_legacy_pack_keeps_no_consent_flow(consent_client, monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_DIR", str(ROOT / "knowledge"))
    config = consent_client.get("/api/config").json()
    assert "consent_required" not in config
    assert "privacy" not in config
    response = consent_client.post("/api/chat", json={"session_id": "legacy", "message": "불안해요"})
    assert response.status_code == 200
    assert response.json()["session_token"]


@pytest.mark.parametrize("document", [
    "본문만 있어요", "---\nconsent_version: missing-fields\n---\n본문",
    "---\n[broken yaml\n---\n본문",
    "---\nconsent_version: v1\nretention_raw_days: true\nretention_summary_days: 365\ndeletion_days: 7\n---\n본문",
    "---\nconsent_version: v1\nconsent_version: v2\nretention_raw_days: 90\nretention_summary_days: 365\ndeletion_days: 7\n---\n본문",
    "---\nconsent_version: v1\nretention_raw_days: 90\nretention_summary_days: 365\ndeletion_days: 7\n---\n  ",
])
def test_invalid_privacy_stops_startup(monkeypatch, tmp_path, document):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "_privacy.md").write_text(document, encoding="utf-8")
    monkeypatch.setenv("KNOWLEDGE_DIR", str(tmp_path))
    with pytest.raises(consent.PrivacyError), TestClient(main.app):
        pass


@pytest.mark.parametrize("key,value", [("RETENTION_RAW_DAYS", "91"), ("RETENTION_SUMMARY_DAYS", "366")])
def test_retention_mismatch_stops_startup(monkeypatch, tmp_path, key, value):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KNOWLEDGE_DIR", str(PACK))
    monkeypatch.setenv(key, value)
    with pytest.raises(consent.PrivacyError, match="RETENTION"), TestClient(main.app):
        pass


def test_switching_pack_does_not_reuse_another_pack_consent(consent_client, tmp_path, monkeypatch):
    consent_client.post("/api/consent", json={"session_id": "switch", "accepted": True, "consent_version": VERSION})
    other = tmp_path / "other-pack"
    other.mkdir()
    (other / "_privacy.md").write_bytes((PACK / "_privacy.md").read_bytes())
    monkeypatch.setenv("KNOWLEDGE_DIR", str(other))
    response = consent_client.post("/api/chat", json={"session_id": "switch", "message": "불안"})
    assert response.status_code == 409


@pytest.mark.parametrize("scenario", ["accept", "decline", "config-failure", "legacy"])
def test_ui_consent_and_deletion_flow_without_network(consent_client, scenario):
    """Execute the real client against an in-memory DOM/fetch, with no HTTP server."""
    import subprocess

    config = consent_client.get("/api/config").json()
    config["privacy"]["body"] = '<img src=x onerror="throw new Error()">\n' + config["privacy"]["body"]
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const spec = JSON.parse(fs.readFileSync(0, 'utf8'));
class Node {
  constructor() { this.hidden = true; this.disabled = false; this.value = ''; this.children = [];
    this.listeners = {}; this.style = {}; this._text = ''; this.scrollHeight = 30;
    this.classList = {toggle() {}}; }
  set textContent(value) { this._text = value; this.children = []; }
  set innerHTML(value) { assert.ok(value.startsWith('<svg '), 'only the fixed avatar SVG may use HTML'); }
  get textContent() { return this._text; }
  appendChild(node) { this.children.push(node); }
  setAttribute() {}
  querySelectorAll() { return []; }
  addEventListener(name, action) { this.listeners[name] = action; }
  scrollIntoView() {}
  focus() {}
  remove() {}
  fire(name) { return this.listeners[name]({preventDefault() {}}); }
}
const nodes = new Map();
const node = id => { if (!nodes.has(id)) nodes.set(id, new Node()); return nodes.get(id); };
const makeStorage = () => ({data: {}, getItem(k) {return this.data[k] || null;},
  setItem(k,v) {this.data[k] = v;}, removeItem(k) {delete this.data[k];}});
const localStorage = makeStorage(), sessionStorage = makeStorage();
const requests = [], copies = [];
let resolveConfig, confirmResult = false, confirmations = 0;
const code = 'ABCD-EFGH-JK23';
const configPromise = new Promise(resolve => {resolveConfig = resolve;});
const context = {
  document: {getElementById: node, querySelector: node, querySelectorAll() {return [];},
    createElement() {return new Node();}, createTextNode(text) {const n = new Node(); n.textContent = text; return n;}},
  window: {location: {href: 'http://test.local/'}, history: {replaceState() {}},
    matchMedia() {return {matches: true};}, setTimeout(f) {f();},
    confirm() {confirmations++; return confirmResult;}},
  navigator: {clipboard: {writeText(text) {copies.push(text); return Promise.resolve();}}},
  localStorage, sessionStorage, URL, crypto: {randomUUID() {return 'synthetic-session';}},
  console: {warn() {}},
  fetch(url, options) {
    requests.push({url, payload: options && JSON.parse(options.body)});
    if (url === '/api/config') return configPromise;
    const payload = JSON.parse(options.body);
    let data;
    if (url === '/api/consent') {
      data = payload.accepted ? {accepted: true, delete_code: code, session_token: 'synthetic-token',
        participant_id: 'p_synthetic', participant_ticket: 'ticket', reply: '첫 인사와 첫 질문'} :
        {accepted: false, reply: '말로 하기 어려우면 전화로도 도움을 받을 수 있어요. 109 · 1588-9191 · 119'};
    } else if (url === '/api/session/delete') {
      data = {deleted: true, session_id: payload.session_id || 'previous-session', reply: '내 기록을 지웠습니다.'};
    } else { data = {reply: '합성 답변', turn: 1, limit_reached: false}; }
    return Promise.resolve({ok: true, json() {return Promise.resolve(data);}});
  }
};
const tick = async () => { for(let i=0; i<5; i++) await new Promise(setImmediate); };
(async () => {
  node('message-input').disabled = true;
  vm.runInNewContext(spec.source, context);
  node('message-input').value = '동의 전 합성 입력';
  node('chat-form').fire('submit');
  assert.deepEqual(requests.map(r => r.url), ['/api/config']);
  let config = spec.config;
  if (spec.scenario === 'legacy') config = {mode: 'intake', intake_schema: true, ui: {}};
  resolveConfig({ok: spec.scenario !== 'config-failure', json() {return Promise.resolve(config);}});
  await tick();
  if (spec.scenario === 'config-failure') {
    assert.equal(node('message-input').disabled, true);
    assert.equal(node('messages').children.length, 0);
    assert.ok(node('status').textContent.includes('109'));
  } else if (spec.scenario === 'legacy') {
    assert.equal(node('message-input').disabled, false);
    assert.equal(node('messages').children.length, 1);
    assert.equal(node('consent-card').hidden, true);
  } else {
    assert.equal(node('message-input').disabled, true);
    assert.equal(node('consent-card').hidden, false);
    assert.equal(node('consent-notice').textContent, config.privacy.body);
    assert.equal(node('messages').children.length, 0);
    node('chat-form').fire('submit');
    assert.equal(requests.length, 1);
    if (spec.scenario === 'decline') {
      node('consent-decline').fire('click'); await tick();
      assert.equal(node('message-input').disabled, true);
      assert.equal(sessionStorage.getItem('lmwiki_session_token'), null);
      assert.equal(requests[1].payload.accepted, false);
      assert.equal(node('messages').children.length, 1);
      node('reset-session').fire('click');
      assert.equal(node('consent-card').hidden, false);
      assert.equal(node('messages').children.length, 0);
    } else {
      node('consent-accept').fire('click'); await tick();
      assert.equal(node('message-input').disabled, false);
      assert.equal(node('consent-card').hidden, true);
      assert.equal(node('delete-code-value').textContent, code);
      assert.equal(node('delete-code-card').hidden, false);
      assert.equal(node('delete-session').hidden, false);
      assert.equal(JSON.stringify(localStorage.data).includes(code), false);
      assert.equal(JSON.stringify(sessionStorage.data).includes(code), false);
      node('copy-delete-code').fire('click'); await tick();
      assert.deepEqual(copies, [code]);
      node('delete-code-input').value = 'ZZZZ-YYYY-XXXX';
      node('delete-code-form').fire('submit'); await tick();
      assert.equal(requests.at(-1).payload.delete_code, 'ZZZZ-YYYY-XXXX');
      assert.equal(node('message-input').disabled, false);
      const count = requests.length;
      node('delete-session').fire('click'); await tick();
      assert.equal(requests.length, count);
      confirmResult = true;
      node('delete-session').fire('click'); await tick();
      assert.equal(confirmations, 2); // One confirmation per click; the first was cancelled.
      assert.equal(requests.at(-1).payload.session_token, 'synthetic-token');
      assert.equal(node('delete-code-value').textContent, '');
      assert.equal(sessionStorage.getItem('lmwiki_session_token'), null);
      assert.equal(node('consent-card').hidden, false);
      assert.equal(node('message-input').disabled, true);
      assert.equal(node('messages').children.length, 0);
    }
  }
  process.stdout.write('UI scenario passed: ' + spec.scenario);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    result = subprocess.run(["node", "-e", script], input=json.dumps({
        "scenario": scenario, "config": config,
        "source": (ROOT / "static/app.js").read_text(encoding="utf-8"),
    }), text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "UI scenario passed: " + scenario
