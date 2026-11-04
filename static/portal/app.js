"use strict";
const $ = id => document.getElementById(id);
let csrf = "", org = "", permissions = [], offset = 0, selected = null, userOrganizations = [];
const portalMode = document.body.dataset.portalMode === "admin" ? "admin" : "institution";
const notice = text => { $("notice").textContent = text || ""; };
function el(tag, text, cls) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; }
function button(label, action, secondary = true) { const b = el("button", label, secondary ? "secondary" : ""); b.type = "button"; b.onclick = () => work(action); return b; }
async function api(path, method = "GET", body) {
  const response = await fetch("/api/portal" + path, {method, credentials:"same-origin", cache:"no-store",
    headers:{"Content-Type":"application/json", "X-CSRF-Token":csrf}, body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) clearWorkspace();
    throw new Error(typeof data.detail === "string" ? data.detail : "처리하지 못했습니다. 다시 시도해 주세요.");
  }
  return data;
}
function clearWorkspace() {
  $("workspace").hidden = true; $("verify").hidden = true; $("email-verify").hidden = true; $("signup").hidden = true;
  $("registration-panel").hidden = true; $("testbed-panel").hidden = true; $("admin-denied").hidden = true; $("login").hidden = false;
  for (const id of ["cases","metrics","links","members","devices","registration-requests","registration-users","org-list","testbed-result"]) $(id).replaceChildren();
  for (const id of ["org","testbed-org","registration-org"]) $(id).replaceChildren();
  for (const id of ["search","management","registration-email","org-new-name","invite-email","new-email"]) $(id).value = "";
  $("session-info").textContent = "";
  $("report").replaceChildren(el("h2","접수 보고서")); $("link-result").replaceChildren(); selected = null; org = ""; permissions = []; userOrganizations = [];
}
const emailMode = document.body.dataset.emailLogin === "true";
const googleMode = document.body.dataset.googleLogin === "true";
if (portalMode === "admin") {
  $("portal-title").textContent = "마음 접수 · 관리자 대시보드";
  $("portal-subtitle").textContent = "기관과 등록 승인을 관리하고 합성 TESTBED를 시작합니다.";
  $("institution-switch").hidden = false;
}
$("google-login-options").hidden = !googleMode;
$("email-login-details").open = !googleMode;
$("email-login-details").querySelector("summary").hidden = !googleMode;
let pendingEmail = "";
let isRegistrar = false;
if (emailMode) {
  $("email-login-hint").hidden = false;
  $("signup-open").hidden = false;
  $("invite-accept").closest("details").hidden = true;
}
async function work(fn) { notice(""); try { await fn(); } catch(e) { notice(e.message); } }
function form(id, fn) { $(id).onsubmit = async event => {
  event.preventDefault(); const submit = event.submitter;
  if (submit?.disabled) return;
  if (submit) submit.disabled = true;
  try { await work(fn); } finally { if (submit) submit.disabled = false; }
}; }
function query() { return "?org_id=" + encodeURIComponent(org); }
function has(p) { return permissions.includes(p); }
const intakeStatus = status => status === "complete" ? "센터 보고서 등록" : "접수 진행 중";
const reviewStatus = status => ({unreviewed:"상담사 미확인",reviewed:"상담사 검토 완료",needs_followup:"추가 확인 필요"}[status] || "상담사 미확인");
const evidenceStatus = status => ({confirmed:"내담자 진술",answered:"내담자 진술",unclear:"추가 확인 필요",unconfirmed:"미확인",declined:"답변하지 않음",not_applicable:"해당 없음"}[status] || "미확인");
async function load() {
  const me = await api("/me"); csrf = me.csrf;
  isRegistrar = Boolean(me.registrar);
  userOrganizations = me.organizations || [];
  $("email-verify").hidden = true; $("signup").hidden = true;
  $("admin-switch").hidden = portalMode !== "institution" || !isRegistrar;
  $("registration-panel").hidden = true;
  $("testbed-panel").hidden = true;
  $("admin-denied").hidden = true;
  $("session-info").hidden = !emailMode || me.state !== "verified";
  $("session-info").textContent = emailMode && me.state === "verified"
    ? me.email + " · 이 브라우저에서 " + new Date(me.expires_at * 1000).toLocaleString() + "까지 로그인 유지"
    : "";
  $("code-form").hidden = me.verification === "email_link";
  $("send-code").textContent = me.verification === "email_link" ? "이메일 확인 링크 받기" : "인증번호 받기";
  for (const id of ["invite-accept", "password-form", "email-form"]) $(id).closest("details").hidden = !me.account_changes;
  $("invite-form").hidden = !me.account_changes;
  $("login").hidden = true; $("verify").hidden = me.state !== "pending_device"; $("workspace").hidden = me.state !== "verified";
  if (emailMode && me.state !== "verified") { clearWorkspace(); return; }
  if (me.state === "pending_device") { $("remember").checked=false; $("code").value=""; $("send-code").focus(); return; }
  if (portalMode === "admin") {
    $("institution-toolbar").hidden = true; $("layout").hidden = true; $("link-panel").hidden = true; $("member-panel").hidden = true;
    if (!isRegistrar) {
      $("admin-denied").hidden = false; $("account-panel").hidden = true;
      notice("이 계정에는 전역 관리자 권한이 없습니다. 기관 포털을 이용해 주세요.");
      return;
    }
    $("registration-panel").hidden = false; $("testbed-panel").hidden = false; $("account-panel").hidden = false;
    $("account-title").textContent = "내 기기 및 계정";
    configureTestbed(userOrganizations);
    await Promise.all([loadOrganizations(), loadDirectory(), loadDevices()]);
    return;
  }
  $("institution-toolbar").hidden = false; $("account-panel").hidden = false; $("member-panel").hidden = false; $("account-title").textContent = "기기 및 담당자 관리";
  $("org").replaceChildren(...me.organizations.map(o => { const option = el("option", o.name); option.value = o.id; option.dataset.permissions = JSON.stringify(o.permissions); return option; }));
  const requestedOrg = new URLSearchParams(location.search).get("org_id");
  if (me.organizations.some(o => o.id === requestedOrg)) org = requestedOrg;
  if (me.organizations.some(o => o.id === org)) $("org").value = org;
  if (!me.organizations.length) {
    clearInstitutionContext();
    notice("현재 접근 가능한 기관이 없습니다. 내 기기 관리는 계속 이용할 수 있습니다.");
    await loadDevices();
    return;
  }
  await selectOrg();
}

function showEmailCode(result) {
  csrf = result.csrf;
  $("login").hidden = true; $("signup").hidden = true; $("verify").hidden = true; $("workspace").hidden = true;
  $("email-verify").hidden = false; $("email-code").value = "";
  const link = result.state === "email_link";
  $("email-code-form").hidden = link;
  $("email-verify").querySelector("h2").textContent = link ? "Gmail에서 로그인 링크 확인" : "이메일 인증번호 입력";
  $("email-resend").textContent = link ? "이메일 링크 다시 받기" : "인증번호 다시 받기";
  $("email-code-status").textContent = result.message;
  (link ? $("email-back") : $("email-code")).focus();
}
async function startEmail() {
  const result = await api("/auth/email-start", "POST", {email: pendingEmail});
  showEmailCode(result);
}
async function loadDirectory() {
  const data = await api("/registrations");
  const chosen = $("registration-org").value;
  $("registration-org").replaceChildren(...data.organizations.map(o => {
    const option = el("option", o.name); option.value = o.id; return option;
  }));
  if (data.organizations.some(o => o.id === chosen)) $("registration-org").value = chosen;
  $("registration-requests").replaceChildren();
  if (!data.requests.length) $("registration-requests").append(el("p", "승인 대기 중인 신청이 없습니다."));
  data.requests.forEach(r => {
    const row = el("div"); row.append(el("span", r.email + " · " + new Date(r.requested_at * 1000).toLocaleString()));
    row.append(button("기관·권한 선택 후 승인", () => {
      $("registration-email").value = r.email; $("registration-role").value = "summary";
      $("registration-org").focus(); notice("소속 기관과 권한을 확인한 뒤 이메일 등록 / 신청 승인 버튼을 눌러 주세요.");
    }), button("신청 거절", async () => { await api("/registrations/reject", "POST", {email:r.email}); await loadDirectory(); }));
    $("registration-requests").append(row);
  });
  const names = new Map(data.organizations.map(o => [o.id, o.name]));
  $("registration-users").replaceChildren(...data.registered.map(r => el("p", r.email + " · " + (names.get(r.org_id) || r.org_id) + " · " + (r.active ? "등록됨" : "중지됨"))));
}
async function loadOrganizations() {
  const data = await api("/organizations");
  $("org-list").replaceChildren();
  if (!data.organizations.length) $("org-list").append(el("p", "등록된 기관이 없습니다."));
  data.organizations.forEach(o => {
    const row = el("div", undefined, "row");
    const input = el("input"); input.value = o.name; input.maxLength = 80; input.setAttribute("aria-label", o.name + " 기관 이름");
    row.append(el("span", o.name + " · " + (o.active ? "활성" : "비활성") + " · 담당자 " + o.members + "명"), input,
      button("이름 변경", async () => { await api("/organizations/" + encodeURIComponent(o.id), "PATCH", {name: input.value, active: o.active}); await reloadOrganizations(); }),
      button(o.active ? "비활성화" : "활성화", async () => { await api("/organizations/" + encodeURIComponent(o.id), "PATCH", {name: o.name, active: !o.active}); await reloadOrganizations(); }));
    $("org-list").append(row);
  });
}
async function reloadOrganizations() { await load(); }
function clearInstitutionContext() {
  org = ""; permissions = []; offset = 0; selected = null;
  for (const id of ["cases","metrics","links","members"]) $(id).replaceChildren();
  $("link-result").replaceChildren();
  $("report").replaceChildren(el("h2","접수 보고서"),el("p","접근 가능한 기관을 선택해 주세요."));
  $("layout").hidden = true; $("link-panel").hidden = true; $("member-panel").hidden = true;
}
function configureTestbed(organizations) {
  const chosen = $("testbed-org").value;
  $("testbed-org").replaceChildren(...organizations.map(o => {
    const option = el("option", o.name); option.value = o.id; option.dataset.permissions = JSON.stringify(o.permissions || []); return option;
  }));
  if (organizations.some(o => o.id === chosen)) $("testbed-org").value = chosen;
  updateTestbedActions();
}
function updateTestbedActions() {
  const option = $("testbed-org").selectedOptions[0];
  const selectedPermissions = option ? JSON.parse(option.dataset.permissions || "[]") : [];
  const canRead = selectedPermissions.includes("report:read");
  const canIssue = selectedPermissions.includes("link:issue");
  const selectedOrg = option?.value || "";
  $("testbed-start").disabled = !canIssue;
  $("testbed-open-org").href = canRead ? "/portal?org_id=" + encodeURIComponent(selectedOrg) : "/portal";
  $("testbed-open-org").setAttribute("aria-disabled", String(!canRead));
  $("testbed-open-org").tabIndex = canRead ? 0 : -1;
  $("testbed-permission").textContent = !option ? "접근 가능한 소속 기관이 없습니다." : !canRead && !canIssue ? "이 기관을 보거나 테스트 링크를 발급할 권한이 없습니다." : !canRead ? "기관 화면 열람 권한이 없습니다." : !canIssue ? "테스트 링크 발급 권한이 없습니다." : "기관 화면 열람과 테스트 링크 발급이 가능합니다.";
}
async function loadDevices() {
  const devices = await api("/devices"); $("devices").replaceChildren();
  devices.forEach(d => {
    const row = el("div");
    row.append(el("span", new Date(d.created_at * 1000).toLocaleString() + " · " + (d.current ? "현재 기기" : d.revoked ? "해제됨" : "유효")));
    if (!d.revoked) row.append(button(d.current ? "이 기기 해제 후 로그아웃" : "기기 해제", async () => {
      const result = await api("/devices/" + d.id, "DELETE");
      if (d.current || result.current_revoked) {
        clearWorkspace();
        notice("현재 기기를 해제해 로그아웃되었습니다. 다시 로그인해 주세요.");
      } else await loadDevices();
    }));
    $("devices").append(row);
  });
}
async function selectOrg() {
  org = $("org").value; permissions = JSON.parse($("org").selectedOptions[0].dataset.permissions); offset = 0; selected = null;
  $("report").replaceChildren(el("h2","접수 보고서"), el("p","목록에서 접수를 선택해 주세요."));
  $("link-panel").hidden = !has("link:issue"); $("member-panel").hidden = !has("member:manage"); $("layout").hidden = !has("report:read");
  $("link-result").replaceChildren(); await refresh();
}
async function refresh() {
  if (has("report:read")) {
    const sum = await api("/summary" + query());
    $("metrics").replaceChildren(...[["전체 접수",sum.total],["전달 완료",sum.complete],["미확인",sum.unreviewed]].map(([label,n]) => { const d=el("div",undefined,"metric"); d.append(el("strong",n),el("span",label)); return d; }));
    await list();
  }
  if (has("link:issue")) {
    const links=await api("/links"+query()); $("links").replaceChildren();
    links.slice(0,8).forEach(l => { const d=el("div"); d.append(el("span",l.management_id+" · "+(l.revoked?"회수됨":l.consumed?"접수됨":"미사용")));
      if(!l.revoked&&!l.consumed) d.append(button("링크 회수",async()=>{await api("/links/"+l.id+query(),"DELETE"); await refresh();})); $("links").append(d); });
  }
  await loadDevices();
  if(has("member:manage")) {
    const members=await api("/members"+query()); $("members").replaceChildren();
    members.forEach(m=>{ const row=el("div");row.append(el("span",m.user_id+" · "+m.permissions.join(", ")+" · "+(m.active?"활성":"중지")));
      row.append(button(m.active?"소속 회수":"소속 복원",async()=>{await api("/members/"+encodeURIComponent(m.user_id),"PATCH",{org_id:org,permissions:m.permissions,active:!m.active});await load();}));$("members").append(row); });
  }
}
async function list() {
  const data=await api("/intakes"+query()+"&search="+encodeURIComponent($("search").value)+"&offset="+offset);
  $("cases").replaceChildren();
  if(!data.items.length) $("cases").append(el("p","접수 내역이 없습니다."));
  data.items.forEach(item=>{
    const b=button("",()=>showReport(item.id));
    b.append(el("span",item.management_id,"case-title"),el("span","저장 "+new Date(item.updated_at||item.created_at).toLocaleString(),"case-meta"));
    const badges=el("span",undefined,"case-badges");
    if(/^TEST-/.test(item.management_id)) badges.append(el("span","TESTBED 합성","badge attention"));
    badges.append(el("span",intakeStatus(item.status),"badge"),el("span",reviewStatus(item.review_status),"badge"+(item.review_status==="needs_followup"?" attention":"")));
    b.append(badges);
    b.className="case";b.setAttribute("aria-current",String(item.id===selected));$("cases").append(b);
  }); $("prev").disabled=offset===0;$("next").disabled=data.items.length<20;
}
async function showReport(id) {
  const r=await api("/intakes/"+id+query());selected=id;
  const latestReview=r.reviews?.length?r.reviews[r.reviews.length-1].status:"unreviewed";
  const reportReviewStatus=r.review_status||latestReview;
  const target=$("report");target.replaceChildren(el("h2",r.management_id+" 접수 보고서"));
  const meta=el("div",undefined,"report-meta");
  [["관리번호",r.management_id],["접수 상태",intakeStatus(r.status)],["검토 상태",reviewStatus(reportReviewStatus)],["저장 시각·버전",new Date(r.updated_at).toLocaleString()+" · v"+r.version]].forEach(([label,value])=>meta.append(el("p",label+": "+value)));
  if(/^TEST-/.test(r.management_id)) meta.append(el("p","자료 구분: TESTBED 합성 자료"));
  target.append(meta);
  if(r.summary.red_flags?.length) target.append(el("p","사람 확인 필요: 저장된 확인 신호가 있습니다. 상담사가 내용을 직접 확인해 주세요."));
  const slots=r.summary.slots||{};
  const evidence=r.summary.slot_evidence||r.slot_evidence||{};
  const visibleKeys=Object.keys(r.slot_labels).filter(key=>key!=="track" && (Object.prototype.hasOwnProperty.call(evidence,key)||Boolean(slots[key])));
  const summarySection=el("div",undefined,"report-section"); summarySection.append(el("h3","핵심 요약"));
  const detailSection=el("div",undefined,"report-section"); detailSection.append(el("h3","세부 항목"));
  const coreKeys=visibleKeys.filter(key=>["chief_complaint","expectation"].includes(key));
  const detailKeys=visibleKeys.filter(key=>!["chief_complaint","expectation"].includes(key));
  if(!coreKeys.length) summarySection.append(el("p","현재 확인된 핵심 요약이 없습니다.","hint"));
  if(!detailKeys.length) detailSection.append(el("p","현재 확인된 세부 항목이 없습니다.","hint"));
  visibleKeys.forEach(key=>{
    const label=r.slot_labels[key]; const item=evidence[key]||{}; const state=item.status||(slots[key]?"answered":"unconfirmed");
    const value=item.value||slots[key]||(state==="declined"?"답변하지 않음":state==="not_applicable"?"해당 없음":"미확인");
    const field=el("div",undefined,"field");field.append(el("strong",label),el("span",evidenceStatus(state),"field-state"),el("p",value));
    if(has("raw:read") && !r.raw_expired) (r.sources[key]||[]).forEach(source=>{const sourceButton=button("출처 #"+source.seq,async()=>{await loadRaw();const t=document.getElementById("turn-"+source.day+"-"+source.seq);if(t){t.tabIndex=-1;t.focus();t.scrollIntoView({block:"center"});}});sourceButton.className="secondary source-button";field.append(sourceButton);});
    (coreKeys.includes(key)?summarySection:detailSection).append(field);
  });
  target.append(summarySection,detailSection);
  const requestSection=el("div",undefined,"report-section");requestSection.append(el("h3","센터 요청"));
  if(r.summary.center_requests?.length) r.summary.center_requests.forEach((v,index)=>{const field=el("div",undefined,"field");field.append(el("strong",v.label||v.category||"센터에 전할 내용"),el("span",evidenceStatus(v.status||"confirmed"),"field-state"),el("p",v.text));if(has("raw:read")&&!r.raw_expired)(r.sources["center_request:"+index]||[]).forEach(source=>{const sourceButton=button("원문 출처 #"+source.seq,async()=>{await loadRaw();const t=document.getElementById("turn-"+source.day+"-"+source.seq);if(t){t.tabIndex=-1;t.focus();t.scrollIntoView({block:"center"});}});sourceButton.className="secondary source-button";field.append(sourceButton);});requestSection.append(field);});
  else requestSection.append(el("p","별도로 등록된 센터 요청이 없습니다.","hint"));
  target.append(requestSection);
  const reviewSection=el("div",undefined,"report-section");reviewSection.append(el("h3","상담사 검토 상태"),el("p",reviewStatus(reportReviewStatus)+" · 센터 보고서 등록과 상담사 검토는 서로 다른 단계입니다.","hint"));target.append(reviewSection);
  if(has("review:write")) target.append(button("담당자 확인 완료",async()=>{await api("/intakes/"+id+"/review","POST",{org_id:org,status:"reviewed"});await showReport(id);await refresh();}),button("추가 확인 필요",async()=>{await api("/intakes/"+id+"/review","POST",{org_id:org,status:"needs_followup"});await showReport(id);await refresh();}));
  r.reviews.forEach(v=>target.append(el("p",v.actor_id+" · "+(v.status==="reviewed"?"확인 완료":"추가 확인 필요")+" · "+new Date(v.created_at).toLocaleString(),"hint")));
  const raw=el("div");raw.id="raw";
  const sourceSection=el("div",undefined,"report-section");sourceSection.append(el("h3","원문 출처"));
  if(r.raw_expired) sourceSection.append(el("p","원문 보관 기간이 만료되었습니다."));
  else if(has("raw:read")) sourceSection.append(button("저장 원문 열기",loadRaw));
  else sourceSection.append(el("p","이 계정에는 원문 열람 권한이 없습니다."));
  target.append(sourceSection);
  async function loadRaw(){
    const data=await api("/intakes/"+id+"/transcript"+query()+ "&request=read");
    raw.replaceChildren(el("h3","저장 원문 · 직접 식별정보 치환"));
    data.documents.forEach(doc=>doc.turns.filter(t=>["user","assistant"].includes(t.role)).forEach(t=>{const item=el("div",undefined,"turn "+t.role);item.id="turn-"+doc.day+"-"+t.seq;item.append(el("strong",doc.day+" #"+t.seq+" "+(t.role==="user"?"내담자":"도우미")),el("p",t.text));raw.append(item);}));
    if(raw.children.length===1) raw.append(el("p","저장된 발화가 없습니다."));
  }
  sourceSection.append(raw);target.tabIndex=-1;target.focus();await list();
}
$("google-login").onclick = () => work(async () => {
  $("google-login").disabled = true;
  try {
    const response = await fetch("/api/portal/auth/google-start", {method:"POST", credentials:"same-origin", cache:"no-store", headers:{"Content-Type":"application/json"}, body:JSON.stringify({return_to:portalMode === "admin" ? "/portal/admin" : "/portal"})});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Google 로그인을 시작하지 못했습니다.");
    location.assign(data.url);
  } finally { $("google-login").disabled = false; }
});
form("login-form",async()=>{
  if (emailMode) { pendingEmail = $("email").value.trim(); await startEmail(); return; }
  const result=await api("/auth/login","POST",{email:$("email").value,password:$("password").value});$("password").value="";csrf=result.csrf;await load();
});
form("email-code-form", async () => {
  const result = await api("/auth/email-login-verify", "POST", {code:$("email-code").value});
  $("email-code").value = ""; csrf = result.csrf; await load();
});
$("email-resend").onclick = () => work(async () => {
  $("email-resend").disabled = true;
  try { await startEmail(); } finally { $("email-resend").disabled = false; }
});
$("email-back").onclick = () => work(async () => {
  await api("/auth/email-cancel", "POST", {}); clearWorkspace(); $("email-verify").hidden = true; $("email").focus();
});
$("signup-open").onclick = () => { notice(""); $("login").hidden = true; $("signup").hidden = false; $("signup-email").value = $("email").value; $("signup-email").focus(); };
$("signup-back").onclick = () => { $("signup").hidden = true; $("login").hidden = false; notice(""); $("email").focus(); };
form("signup-form", async () => {
  const result = await api("/auth/apply", "POST", {email:$("signup-email").value});
  $("signup-status").textContent = result.message;
});
form("org-create-form", async () => {
  await api("/organizations", "POST", {name: $("org-new-name").value});
  $("org-new-name").value = ""; await reloadOrganizations();
});
form("registration-form", async () => {
  const result = await api("/registrations", "POST", {email:$("registration-email").value, org_id:$("registration-org").value, role:$("registration-role").value});
  $("registration-email").value = ""; await loadDirectory(); notice(result.message);
});
$("send-code").onclick=()=>work(async()=>{const r=await api("/auth/device-challenge","POST",{});$("send-status").textContent=r.verification==="email_link"?"이메일을 보냈습니다. 로그인한 이 브라우저에서 확인 링크를 열어 주세요.":"로컬 메일함에 인증번호를 캡처했습니다. 재전송은 "+r.retry_after+"초 후 가능합니다.";if(r.verification!=="email_link")$("code").focus();});
form("code-form",async()=>{const r=await api("/auth/device-verify","POST",{code:$("code").value,remember:$("remember").checked});csrf=r.csrf;$("code").value="";await load();});
async function logout(){await api("/auth/logout","POST",{});csrf="";clearWorkspace();}
$("logout").onclick=()=>work(logout);$("pending-logout").onclick=()=>work(logout);
$("admin-logout").onclick=()=>work(logout);$("admin-refresh").onclick=()=>work(load);
$("org").onchange=()=>work(selectOrg);$("refresh").onclick=()=>work(refresh);
$("testbed-org").onchange=updateTestbedActions;
$("testbed-open-org").onclick=event=>{if($("testbed-open-org").getAttribute("aria-disabled") === "true")event.preventDefault();};
form("testbed-form",async()=>{
  const orgId=$("testbed-org").value;
  const result=await api("/testbed","POST",{org_id:orgId});
  if(result.synthetic!==true || !/^TEST-[A-Za-z0-9-]+$/.test(result.management_id||"")) throw new Error("합성 TEST 접수를 확인하지 못했습니다.");
  const target=new URL(result.url,location.origin);
  if(!["http:","https:"].includes(target.protocol) || target.origin!==location.origin) throw new Error("안전한 테스트 링크를 확인하지 못했습니다.");
  const link=el("a","새 챗봇 테스트 열기");link.href=target.href;link.target="_blank";link.rel="noopener noreferrer";
  $("testbed-result").replaceChildren(el("strong","관리번호 "+result.management_id),el("p","선택 기관의 합성 접수로 저장되며 집계·목록·보고서에서 TEST 관리번호로 구분됩니다."),link);
});
form("search-form",async()=>{offset=0;await list();});$("prev").onclick=()=>work(async()=>{offset=Math.max(0,offset-20);await list();});$("next").onclick=()=>work(async()=>{offset+=20;await list();});
form("link-form",async()=>{const r=await api("/links","POST",{org_id:org,management_id:$("management").value});const a=el("a",r.url);a.href=r.url;a.target="_blank";a.rel="noopener noreferrer";$("link-result").replaceChildren(a,button("링크 복사",()=>navigator.clipboard.writeText(r.url)));await refresh();});
form("invite-form",async()=>{await api("/invitations","POST",{org_id:org,email:$("invite-email").value,permissions:$("invite-role").value==="summary"?["report:read"]:["report:read","raw:read","review:write"]});notice("초대 메일을 로컬 메일함에 캡처했습니다.");});
form("invite-accept",async()=>{await api("/auth/accept-invitation","POST",{token:$("invite-token").value,password:$("invite-password").value});$("invite-token").value="";$("invite-password").value="";notice("초대를 수락했습니다. 로그인 후 이메일로 기기를 확인해 주세요.");});
form("password-form",async()=>{await api("/auth/password","POST",{current_password:$("old-password").value,new_password:$("new-password").value});$("old-password").value="";$("new-password").value="";clearWorkspace();notice("비밀번호를 변경했습니다. 다시 로그인하고 기기를 확인해 주세요.");});
form("email-form",async()=>{await api("/auth/email-challenge","POST",{email:$("new-email").value,password:$("email-password").value});$("email-password").value="";notice("새 이메일 확인 메일을 캡처했습니다. 아직 이메일은 변경되지 않았습니다.");});
form("email-verify-form",async()=>{await api("/auth/email-verify","POST",{token:$("email-token").value});$("email-token").value="";clearWorkspace();notice("이메일을 변경했습니다. 새 이메일로 로그인하고 기기를 확인해 주세요.");});
// Prevent restored browser history from exposing a stale report after logout.
window.addEventListener("pageshow",event=>{if(event.persisted){clearWorkspace();work(load);}});
load().catch(async e=>{
  clearWorkspace();
  if (emailMode) {
    try { const pending=await api("/auth/email-pending"); pendingEmail=pending.email; showEmailCode(pending); return; }
    catch (_) { /* No pending attempt is the normal logged-out state. */ }
  }
  if(!e.message.includes("로그인"))notice(e.message);
}).finally(() => { $("session-loading").hidden = true; });
