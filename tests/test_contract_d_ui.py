"""Run the actual static scripts against in-memory DOM/fetch; no network or models."""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

BROWSER = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const spec = JSON.parse(fs.readFileSync(0, 'utf8'));
class Element {
  constructor(tag = '') {
    this.tag = tag; this.hidden = true; this.disabled = false; this.value = '';
    this.children = []; this.listeners = {}; this.style = {}; this._text = '';
    this.scrollHeight = 30; this.classList = {toggle() {}};
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(n => n.textContent).join(''); }
  set innerHTML(value) { assert.ok(value.startsWith('<svg '), 'all dynamic values must use textContent'); }
  appendChild(node) { node.parent = this; this.children.push(node); return node; }
  append(...nodes) { nodes.forEach(n => this.appendChild(n)); }
  removeChild(node) { this.children = this.children.filter(n => n !== node); }
  get firstChild() { return this.children[0]; }
  remove() { if (this.parent) this.parent.removeChild(this); }
  setAttribute(key, value) { this[key] = value; }
  getAttribute(key) { return this[key]; }
  querySelectorAll() { return []; }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  scrollIntoView() {}
  showModal() {}
  close() {}
  focus() {}
  fire(name) { return this.listeners[name]({preventDefault() {}}); }
}
const nodes = new Map();
const node = id => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
const storage = () => ({data: {}, getItem(k) {return this.data[k] || null;},
  setItem(k,v) {this.data[k] = String(v);}, removeItem(k) {delete this.data[k];}});
const local = storage(), session = storage(), requests = [], copies = [], replaced = [];
local.setItem('lmwiki_participant_id', 'old-management-number');
session.setItem('lmwiki_session_id', 'old-session');
session.setItem('lmwiki_session_token', 'old-token');
session.setItem('lmwiki_consent_version', 'v1');
if (spec.scenario === 'pending-reload') {
  session.setItem('lmwiki_pending_intake_link', JSON.stringify({management_id: '2026-003', link_ticket: 'v1.synthetic'}));
  session.removeItem('lmwiki_session_id'); session.removeItem('lmwiki_session_token');
}
if (spec.scenario === 'pending-chat-reload') {
  session.setItem('lmwiki_pending_chat_request', JSON.stringify({request_id: 'retry-id-123', message: '보존된 재시도 원문', session_id: 'old-session'}));
}
let href = 'http://test.local/';
if (['link', 'retryable', 'mode-only'].includes(spec.scenario)) href += '?keep=yes&management_id=2026-003&link_ticket=v1.synthetic#anchor';
if (spec.scenario === 'invalid-link') href += '?management_id=2026-003';
const closingResponses = [
  {reply: '마지막으로 센터에 미리 전하고 싶은 것이 있으면 골라 주세요. 없으면 바로 보내도 돼요.',
    turn: 9, closing: {stage: 'select'}, quick_replies: [
      {label: '상담 가능한 요일·시간', message: '상담 가능한 요일·시간'},
      {label: '상담사에게 바라는 점', message: '상담사에게 바라는 점'},
      {label: '센터에 묻고 싶은 것', message: '센터에 묻고 싶은 것'},
      {label: '없음, 이대로 보내기', message: '없음, 이대로 보내기', action: 'send'}]},
  {reply: '센터에 전달했어요. 센터에서 확인한 뒤 연락드릴 거예요. 109 · 1588-9191 · 119 · 삭제 코드',
    turn: 10, conversation_ended: true, handoff: {mode: 'center', sent: true}}
];
const config = {mode: 'intake', intake_schema: true, ui: {}, slot_labels: {cause: '원인·계기', chief_complaint: '주 호소'},
  consent_required: spec.mode === 'chat', privacy: {consent_version: 'v1', body: '합성 개인정보 고지'}};
let chatRequestCount = 0;
const context = {
  document: {getElementById: node, querySelector: node, querySelectorAll() {return [];},
    createElement(tag) {return new Element(tag);}, body: new Element('body'),
    createTextNode(text) {const n = new Element(); n.textContent = text; return n;}},
  window: {location: {get href() {return href;}}, history: {replaceState(_state, _title, url) {
    replaced.push(url); href = new URL(url, href).href;
  }}, matchMedia() {return {matches: true};}, setTimeout(f) {f();}},
  navigator: {clipboard: {writeText(text) {copies.push(text); return Promise.resolve();}}},
  localStorage: local, sessionStorage: session, URL, URLSearchParams,
  crypto: {randomUUID() {return 'new-session';}}, console: {warn() {}},
  fetch(url, options) {
    const payload = options && JSON.parse(options.body);
    requests.push({url, payload});
    let ok = true, data;
    if (url === '/api/config') data = config;
    else if (url === '/api/consent') {
      ok = spec.scenario !== 'invalid-link';
      data = ok ? {accepted: true, participant_id: '2026-003', participant_ticket: 'v1.verified', session_token: 'new-token',
        delete_code: 'AAAA-BBBB-CCCC', reply: '첫 질문'} : {detail: '링크가 올바르지 않아요. 센터에 다시 요청해 주세요. 109 · 119'};
    } else if (url === '/api/chat') {
      chatRequestCount += 1;
      data = spec.scenario === 'retryable' && chatRequestCount === 1
        ? {reply: '처리 결과를 확인하지 못했어요.', turn: 1, processing_status: 'retryable', retryable: true}
        : spec.scenario === 'mode-only' && chatRequestCount === 1
          ? {reply: '아직 센터에 보내지 않았어요.', turn: 1, processing_status: 'completed', handoff: {mode: 'center', sent: false}}
          : closingResponses.shift();
    }
    else if (url === '/api/admin/links') data = {management_id: '2026-003', url: 'http://test.local/?management_id=2026-003&link_ticket=v1.synthetic'};
    else if (url === '/api/stats') data = {exists: true, recent_sessions: [{participant_id: '2026-003', session_id: 'session', date: '2026-11-03'}]};
    else if (String(url).startsWith('/api/stats/session?')) data = {turns: [{role: 'user', text: '<script>원문</script>'}],
      summary: {slots: {cause: '모르겠어요'}, center_requests: [{label: '센터에 묻고 싶은 것', text: '<img src=x>주차 가능한가요?'}]}};
    else throw Error('unexpected fetch: ' + url);
    return Promise.resolve({ok, json() {return Promise.resolve(data);}});
  }
};
const tick = async () => {for (let i=0; i<12; i++) await new Promise(setImmediate);};
const walk = el => [el, ...el.children.flatMap(walk)];
(async () => {
  vm.runInNewContext(spec.source, context);
  await tick();
  if (spec.mode === 'stats') {
    node('link-management-id').value = '2026-003';
    await node('link-form').fire('submit'); await tick();
    const issued = requests.find(r => r.url === '/api/admin/links');
    assert.deepEqual(issued.payload, {management_id: '2026-003'});
    assert.ok(node('issued-link').textContent.includes('&link_ticket=v1.synthetic'));
    assert.equal(node('copy-issued-link').disabled, false);
    await node('copy-issued-link').fire('click');
    assert.equal(copies[0], node('issued-link').textContent);
    assert.ok(node('client-list').textContent.includes('관리번호 2026-003'));
    const button = walk(node('client-list')).find(el => el.textContent === '대화 내역 보기');
    button.fire('click'); await tick();
    const detail = node('conversation-turns').textContent;
    ['접수 요약표', '원인·계기', '모르겠어요', '센터에 묻고 싶은 것', '<img src=x>주차 가능한가요?', '<script>원문</script>'].forEach(value => assert.ok(detail.includes(value)));
    return;
  }
  if (spec.scenario === 'pending-chat-reload') {
    assert.equal(node('message-input').value, '보존된 재시도 원문');
    assert.equal(node('chips').hidden, true);
    assert.equal(node('retry-button').hidden, false);
    return;
  }
  assert.equal(node('message-input').disabled, true);
  if (spec.scenario !== 'pending-reload') {
    assert.equal(new URL(href).searchParams.has('management_id'), false);
    assert.equal(new URL(href).searchParams.has('link_ticket'), false);
    assert.ok(!local.data.lmwiki_participant_id || local.data.lmwiki_participant_id !== '2026-003');
    assert.equal(session.getItem('lmwiki_session_token'), null);
  }
  node('consent-accept').fire('click'); await tick();
  const accepted = requests.find(r => r.url === '/api/consent');
  assert.equal(accepted.payload.management_id, '2026-003');
  assert.equal(accepted.payload.link_ticket, spec.scenario === 'invalid-link' ? null : 'v1.synthetic');
  if (spec.scenario === 'invalid-link') {
    assert.equal(node('message-input').disabled, true);
    assert.ok(node('status').textContent.includes('링크가 올바르지'));
    assert.equal(requests.filter(r => r.url === '/api/chat').length, 0);
    return;
  }
  assert.equal(node('message-input').disabled, false);
  assert.equal(local.getItem('lmwiki_participant_id'), '2026-003');
  assert.equal(session.getItem('lmwiki_pending_intake_link'), null);
  assert.equal(node('delete-code-value').textContent, 'AAAA-BBBB-CCCC');
  if (spec.scenario === 'retryable') {
    node('message-input').value = '합성 재시도 원문';
    node('chat-form').fire('submit'); await tick();
    const first = requests.filter(r => r.url === '/api/chat').at(-1);
    assert.equal(node('message-input').value, '합성 재시도 원문');
    assert.equal(node('retry-button').hidden, false);
    node('chat-form').fire('submit'); await tick();
    const second = requests.filter(r => r.url === '/api/chat').at(-1);
    assert.equal(second.payload.request_id, first.payload.request_id);
    assert.equal(requests.filter(r => r.url === '/api/chat').length, 2);
    return;
  }
  if (spec.scenario === 'mode-only') {
    node('message-input').value = '합성 미전달 확인';
    node('chat-form').fire('submit'); await tick();
    assert.notEqual(node('turn-counter').textContent, '전달 완료');
    assert.equal(node('delivery-status').textContent, '저장됨');
    return;
  }
  node('message-input').value = '합성 마지막 일반 답';
  node('chat-form').fire('submit'); await tick();
  let buttons = walk(node('contextual-replies')).filter(el => el.tag === 'button');
  assert.equal(buttons.length, 4);
  const send = buttons.find(el => el.className.includes('reply-suggestion-send'));
  assert.equal(send.textContent, '없음, 이대로 보내기');
  send.fire('click'); await tick();
  assert.equal(requests.at(-1).payload.message, '없음, 이대로 보내기');
  assert.equal(node('message-input').disabled, true);
  assert.equal(node('turn-counter').textContent, '전달 완료');
  assert.ok(!walk(node('messages')).some(el => el.className === 'handoff-card'));
  assert.ok(!node('messages').textContent.includes('기관에 전할 정리'));
  assert.ok(node('messages').textContent.includes('센터에 전달했어요'));
  assert.equal(node('delete-code-card').hidden, false);
})().catch(error => {console.error(error); process.exitCode = 1;});
"""


@pytest.mark.parametrize("scenario", ["link", "pending-reload", "pending-chat-reload", "invalid-link", "retryable", "mode-only", "stats"])
def test_actual_client_scripts_without_network(scenario):
    mode = "stats" if scenario == "stats" else "chat"
    result = subprocess.run(["node", "-e", BROWSER], input=json.dumps({
        "mode": mode, "scenario": scenario,
        "source": (ROOT / "static" / ("stats.js" if mode == "stats" else "app.js")).read_text(),
    }), text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
