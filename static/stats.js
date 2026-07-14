const metricGrid = document.querySelector('#metric-grid');
const trackBars = document.querySelector('#track-bars');
const slotBars = document.querySelector('#slot-bars');
const dailyBars = document.querySelector('#daily-bars');
const recentSessions = document.querySelector('#recent-sessions');
const individualFlags = document.querySelector('#individual-flags');
const individualCount = document.querySelector('#individual-count');
const statusEl = document.querySelector('#stats-status');

function number(value) {
  return new Intl.NumberFormat('ko-KR').format(value ?? 0);
}

function percent(value) {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function appendMetric(label, value, hint) {
  const card = document.createElement('article');
  card.className = 'metric-card';
  const strong = document.createElement('strong');
  strong.textContent = value;
  const span = document.createElement('span');
  span.textContent = label;
  const small = document.createElement('small');
  small.textContent = hint;
  card.append(strong, span, small);
  metricGrid.appendChild(card);
}

function appendBar(container, label, value, max, suffix = '명') {
  const row = document.createElement('div');
  row.className = 'bar-row';
  const top = document.createElement('div');
  top.className = 'bar-top';
  const name = document.createElement('span');
  name.textContent = label;
  const count = document.createElement('b');
  count.textContent = `${number(value)}${suffix}`;
  top.append(name, count);
  const track = document.createElement('div');
  track.className = 'bar-track';
  const fill = document.createElement('div');
  fill.className = 'bar-fill';
  fill.style.width = `${max ? Math.max(4, Math.round((value / max) * 100)) : 0}%`;
  track.appendChild(fill);
  row.append(top, track);
  container.appendChild(row);
}

function severityLabel(value) {
  return { high: '긴급', medium: '주의', low: '관찰' }[value] || value || '관찰';
}

function appendIndividualFlag(record) {
  const card = document.createElement('article');
  card.className = `individual-item severity-${record.severity || 'low'}`;

  const head = document.createElement('div');
  head.className = 'individual-head';

  const title = document.createElement('div');
  const strong = document.createElement('strong');
  strong.textContent = `${record.participant_id} · ${record.track}`;
  const meta = document.createElement('span');
  meta.textContent = `${record.session_id} · 사용자 ${record.user_turns}턴`;
  title.append(strong, meta);

  const severity = document.createElement('span');
  severity.className = `severity-pill severity-${record.severity || 'low'}`;
  severity.textContent = severityLabel(record.severity);
  head.append(title, severity);

  const flags = document.createElement('ul');
  flags.className = 'flag-list';
  (record.flags || []).forEach((flag) => {
    const li = document.createElement('li');
    const label = document.createElement('b');
    label.textContent = flag.label;
    const detail = document.createElement('span');
    detail.textContent = flag.detail;
    li.append(label, detail);
    flags.appendChild(li);
  });

  const details = document.createElement('dl');
  details.className = 'individual-details';
  [
    ['호소', record.chief_complaint || '미확인'],
    ['지지', record.support || '미확인'],
    ['기대', record.expectation || '미확인'],
    ['미확인', record.missing && record.missing.length ? record.missing.join(', ') : '없음'],
  ].forEach(([label, value]) => {
    const dt = document.createElement('dt');
    dt.textContent = label;
    const dd = document.createElement('dd');
    dd.textContent = value;
    details.append(dt, dd);
  });

  card.append(head, flags, details);
  individualFlags.appendChild(card);
}

function renderStats(data) {
  clear(metricGrid);
  clear(trackBars);
  clear(slotBars);
  clear(dailyBars);
  clear(recentSessions);
  clear(individualFlags);

  const totals = data.totals || {};
  appendMetric('개인번호', number(totals.participants), 'participants 테이블');
  appendMetric('세션', number(totals.conversations), 'conversations 테이블');
  appendMetric('대화 턴', number(totals.turns), 'user + assistant + summary');
  appendMetric('위기 세션', number(totals.red_flag_sessions), 'red flag 요약 포함');
  appendMetric('요약 생성', number(totals.summaries), 'intake_summary 적재');
  appendMetric('특이 세션', number(totals.notable_sessions), '사람 검토 triage');
  appendMetric('평균 사용자 턴', number(totals.avg_user_turns_per_conversation), '세션당 입력 수');

  const trackMax = Math.max(1, ...data.track_counts.map((item) => item.count));
  data.track_counts.forEach((item) => appendBar(trackBars, item.track, item.count, trackMax));
  if (!data.track_counts.length) appendBar(trackBars, '아직 적재 없음', 0, 1);

  const slotMax = Math.max(1, ...data.slot_completion.map((item) => item.completed));
  data.slot_completion.slice(0, 9).forEach((item) => {
    appendBar(slotBars, `${item.label} (${percent(item.rate)})`, item.completed, slotMax);
  });

  const dailyMax = Math.max(1, ...data.daily_counts.map((item) => item.conversations));
  data.daily_counts.forEach((item) => {
    appendBar(dailyBars, item.date, item.conversations, dailyMax, '세션');
  });

  data.recent_sessions.forEach((session) => {
    const row = document.createElement('tr');
    [
      session.date,
      session.session_id,
      session.participant_id,
      session.track,
      session.red_flags && session.red_flags.length ? '있음' : '없음',
    ].forEach((text) => {
      const td = document.createElement('td');
      td.textContent = text;
      row.appendChild(td);
    });
    recentSessions.appendChild(row);
  });

  const flagged = data.individual_flags || [];
  individualCount.textContent = `${number(flagged.length)}건`;
  if (!flagged.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-note';
    empty.textContent = '현재 필터에서는 특이 사항이 감지된 세션이 없습니다.';
    individualFlags.appendChild(empty);
  } else {
    flagged.forEach(appendIndividualFlag);
  }
}

async function loadStats() {
  statusEl.textContent = '통계를 불러오는 중입니다.';
  try {
    const response = await fetch('/api/stats?participant_prefix=demo-person-');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    renderStats(data);
    statusEl.textContent = data.exists
      ? `DB: ${data.database} · demo-person- 필터 적용`
      : '아직 data/chatlog.db가 없습니다. scripts/generate_demo_population.py를 실행해 샘플을 적재하세요.';
  } catch (error) {
    statusEl.textContent = `통계를 불러오지 못했습니다: ${error.message}`;
  }
}

loadStats();
