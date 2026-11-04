"use strict";
const $ = id => document.getElementById(id);
let csrf = "", org = "", permissions = [], offset = 0, selected = null;
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
function clearWorkspace() { $("workspace").hidden = true; $("verify").hidden = true; $("email-verify").hidden = true; $("signup").hidden = true; $("registration-panel").hidden = true; $("login").hidden = false; $("cases").replaceChildren(); $("report").replaceChildren(el("h2","접수 보고서")); selected = null; }
const emailMode = document.body.dataset.emailLogin === "true";
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
async function load() {
  const me = await api("/me"); csrf = me.csrf;
  isRegistrar = Boolean(me.registrar);
  $("email-verify").hidden = true; $("signup").hidden = true;
  $("registration-panel").hidden = !me.registrar;
  $("code-form").hidden = me.verification === "email_link";
  $("send-code").textContent = me.verification === "email_link" ? "이메일 확인 링크 받기" : "인증번호 받기";
  for (const id of ["invite-accept", "password-form", "email-form"]) $(id).closest("details").hidden = !me.account_changes;
  $("invite-form").hidden = !me.account_changes;
  $("login").hidden = true; $("verify").hidden = me.state !== "pending_device"; $("workspace").hidden = me.state !== "verified";
  if (emailMode && me.state !== "verified") { clearWorkspace(); return; }
  if (me.state === "pending_device") { $("remember").checked=false; $("code").value=""; $("send-code").focus(); return; }
  $("org").replaceChildren(...me.organizations.map(o => { const option = el("option", o.name); option.value = o.id; option.dataset.permissions = JSON.stringify(o.permissions); return option; }));
  if (me.organizations.some(o => o.id === org)) $("org").value = org;
  if (!me.organizations.length) { notice("현재 접근 가능한 기관이 없습니다."); $("layout").hidden = true; return; }
  await selectOrg();
}

function showEmailCode(result) {
  csrf = result.csrf;
  $("login").hidden = true; $("signup").hidden = true; $("verify").hidden = true; $("workspace").hidden = true;
  $("email-verify").hidden = false; $("email-code").value = "";
  $("email-code-status").textContent = result.message;
  $("email-code").focus();
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
  const devices=await api("/devices"); $("devices").replaceChildren();
  devices.forEach(d=>{ const row=el("div"); row.append(el("span",new Date(d.created_at*1000).toLocaleString()+" · "+(d.revoked?"해제됨":"유효")));
    if(!d.revoked) row.append(button("기기 해제",async()=>{await api("/devices/"+d.id,"DELETE");await load();})); $("devices").append(row); });
  if(has("member:manage")) {
    const members=await api("/members"+query()); $("members").replaceChildren();
    members.forEach(m=>{ const row=el("div");row.append(el("span",m.user_id+" · "+m.permissions.join(", ")+" · "+(m.active?"활성":"중지")));
      row.append(button(m.active?"소속 회수":"소속 복원",async()=>{await api("/members/"+encodeURIComponent(m.user_id),"PATCH",{org_id:org,permissions:m.permissions,active:!m.active});await load();}));$("members").append(row); });
  }
  if (isRegistrar) await loadDirectory();
}
async function list() {
  const data=await api("/intakes"+query()+"&search="+encodeURIComponent($("search").value)+"&offset="+offset);
  $("cases").replaceChildren();
  if(!data.items.length) $("cases").append(el("p","접수 내역이 없습니다."));
  data.items.forEach(item=>{
    const b=button(item.management_id+" · "+(item.status==="complete"?"전달 완료":"진행 중")+"\n"+new Date(item.created_at).toLocaleString()+" · "+(item.review_status==="unreviewed"?"미확인":"확인 기록 있음"),()=>showReport(item.id));
    b.className="case";b.setAttribute("aria-current",String(item.id===selected));$("cases").append(b);
  }); $("prev").disabled=offset===0;$("next").disabled=data.items.length<20;
}
async function showReport(id) {
  const r=await api("/intakes/"+id+query());selected=id;
  const target=$("report");target.replaceChildren(el("h2",r.management_id+" 접수 보고서"));
  target.append(el("p","저장 버전 "+r.version+" · "+new Date(r.updated_at).toLocaleString()+" · "+(r.status==="complete"?"전달 완료":"대화 진행 중"),"hint"));
  if(r.summary.red_flags?.length) target.append(el("p","사람 확인 필요: 저장된 확인 신호가 있습니다. 상담사가 내용을 직접 확인해 주세요."));
  const slots=r.summary.slots||{};
  const common=["chief_complaint","symptom_context","cause","coping","support","expectation"];
  Object.entries(r.slot_labels).filter(([key])=>key!=="track" && (common.includes(key)||slots[key])).forEach(([key,label])=>{
    const field=el("div",undefined,"field");field.append(el("strong",label),el("p",slots[key]||"미확인"));
    if(has("raw:read") && !r.raw_expired) (r.sources[key]||[]).forEach(source=>field.append(button("출처 #"+source.seq,async()=>{await loadRaw();const t=document.getElementById("turn-"+source.day+"-"+source.seq);if(t){t.tabIndex=-1;t.focus();t.scrollIntoView({block:"center"});}})));
    target.append(field);
  });
  if(r.summary.center_requests?.length){const field=el("div",undefined,"field");field.append(el("strong","센터 요청"));r.summary.center_requests.forEach(v=>field.append(el("p",v.label+": "+v.text)));target.append(field);}
  if(has("review:write")) target.append(button("담당자 확인 완료",async()=>{await api("/intakes/"+id+"/review","POST",{org_id:org,status:"reviewed"});await showReport(id);await refresh();}),button("추가 확인 필요",async()=>{await api("/intakes/"+id+"/review","POST",{org_id:org,status:"needs_followup"});await showReport(id);await refresh();}));
  r.reviews.forEach(v=>target.append(el("p",v.actor_id+" · "+(v.status==="reviewed"?"확인 완료":"추가 확인 필요")+" · "+new Date(v.created_at).toLocaleString(),"hint")));
  const raw=el("div");raw.id="raw";
  if(r.raw_expired) target.append(el("p","원문 보관 기간이 만료되었습니다."));
  else if(has("raw:read")) target.append(button("저장 원문 열기",loadRaw));
  else target.append(el("p","이 계정에는 원문 열람 권한이 없습니다."));
  async function loadRaw(){
    const data=await api("/intakes/"+id+"/transcript"+query()+ "&request=read");
    raw.replaceChildren(el("h3","저장 원문 · 직접 식별정보 치환"));
    data.documents.forEach(doc=>doc.turns.filter(t=>["user","assistant"].includes(t.role)).forEach(t=>{const item=el("div",undefined,"turn "+t.role);item.id="turn-"+doc.day+"-"+t.seq;item.append(el("strong",doc.day+" #"+t.seq+" "+(t.role==="user"?"내담자":"도우미")),el("p",t.text));raw.append(item);}));
    if(raw.children.length===1) raw.append(el("p","저장된 발화가 없습니다."));
  }
  target.append(raw);target.tabIndex=-1;target.focus();await list();
}
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
form("registration-form", async () => {
  const result = await api("/registrations", "POST", {email:$("registration-email").value, org_id:$("registration-org").value, role:$("registration-role").value});
  $("registration-email").value = ""; await refresh(); notice(result.message);
});
$("send-code").onclick=()=>work(async()=>{const r=await api("/auth/device-challenge","POST",{});$("send-status").textContent=r.verification==="email_link"?"이메일을 보냈습니다. 로그인한 이 브라우저에서 확인 링크를 열어 주세요.":"로컬 메일함에 인증번호를 캡처했습니다. 재전송은 "+r.retry_after+"초 후 가능합니다.";if(r.verification!=="email_link")$("code").focus();});
form("code-form",async()=>{const r=await api("/auth/device-verify","POST",{code:$("code").value,remember:$("remember").checked});csrf=r.csrf;$("code").value="";await load();});
async function logout(){await api("/auth/logout","POST",{});csrf="";clearWorkspace();}
$("logout").onclick=()=>work(logout);$("pending-logout").onclick=()=>work(logout);
$("org").onchange=()=>work(selectOrg);$("refresh").onclick=()=>work(refresh);
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
});
