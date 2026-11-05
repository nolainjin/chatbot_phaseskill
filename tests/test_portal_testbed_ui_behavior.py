"""Execute the portal test-link and permission paths without network/real records."""
import json
from pathlib import Path
import subprocess

SCRIPT = (Path(__file__).resolve().parents[1] / "static/portal/app.js").read_text()


def run_node(code):
    result = subprocess.run(["node", "-e", code], text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def test_generated_testbed_links_are_same_origin_synthetic_and_report_scoped():
    function = SCRIPT[SCRIPT.index("function renderTestbedResult("):SCRIPT.index('form("testbed-form",')]
    result = run_node("""
const vm=require('node:vm');
function el(tag,text){return {tag,text,children:[],append(...items){this.children.push(...items)},focus(){this.focused=true}};}
const c={el,location:{origin:'https://example.test'},URL,encodeURIComponent};
vm.createContext(c);vm.runInContext(FUNCTION,c);
function run(value,canRead=true){
 const container={replaceChildren(...children){this.children=children},append(...items){this.children.push(...items)}};
 try{c.renderTestbedResult(value,'org-a',container,canRead);return {children:container.children};}catch(e){return {error:e.message};}
}
const valid={synthetic:true,management_id:'TEST-ABC',url:'/?ticket=synthetic'};
console.log(JSON.stringify({valid:run(valid),withoutRead:run(valid,false),external:run({...valid,url:'https://evil.test/'}),notTest:run({...valid,management_id:'REAL-ABC'}),notSynthetic:run({...valid,synthetic:false})}));
""".replace("FUNCTION", json.dumps(function)))
    links = result["valid"]["children"]
    assert links[2]["href"] == "https://example.test/?ticket=synthetic"
    assert links[2]["rel"] == "noopener noreferrer"
    assert links[2]["focused"]
    assert links[3]["children"][0]["href"] == "/portal?org_id=org-a&search=TEST-ABC"
    assert len(result["withoutRead"]["children"]) == 3
    assert all(result[name].get("error") for name in ("external", "notTest", "notSynthetic"))


def test_institution_handler_does_not_issue_without_permission_or_show_other_org_result():
    handler = SCRIPT[SCRIPT.index('$("institution-testbed-start").onclick='):SCRIPT.index('$("open-org-admin").onclick=')]
    result = run_node("""
const vm=require('node:vm');
(async()=>{
 const nodes={'institution-testbed-start':{},'institution-testbed-result':{}};
 let allowed=false,calls=0,rendered=0,resolve;
 const c={$:id=>nodes[id],work:fn=>fn(),has:()=>allowed,org:'org-a',api:()=>{calls++;return new Promise(r=>resolve=r)},renderTestbedResult:()=>rendered++};
 vm.createContext(c);vm.runInContext(HANDLER,c);
 await nodes['institution-testbed-start'].onclick();
 const deniedCalls=calls;
 allowed=true;
 const pending=nodes['institution-testbed-start'].onclick();
 c.org='org-b';resolve({synthetic:true});await pending;
 console.log(JSON.stringify({deniedCalls,calls,rendered,disabled:nodes['institution-testbed-start'].disabled}));
})();
""".replace("HANDLER", json.dumps(handler)))
    assert result == {"deniedCalls": 0, "calls": 1, "rendered": 0, "disabled": False}


def test_completed_additional_content_precedes_accumulated_slots_without_rewriting():
    function = SCRIPT[SCRIPT.index("async function showReport("):SCRIPT.index('$("google-login").onclick')]
    result = run_node("""
const vm=require('node:vm');
function el(tag,text,cls){return {tag,text,cls,children:[],append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},focus(){}};}
(async()=>{
 async function render(status,requests,rawPermission,expired=false){
  const root=el('section');
  const data={management_id:'TEST-UXR',status,review_status:'unreviewed',updated_at:'2026-11-05T00:00:00Z',version:2,reviews:[],raw_expired:expired,
   summary:{red_flags:['synthetic'],slots:{chief_complaint:'원문 그대로: 산책, 화요일'},center_requests:requests},
   slot_labels:{chief_complaint:'호소 문제'},sources:{chief_complaint:[{day:'2026-11-05',seq:1}],'center_request:0':[{day:'2026-11-05',seq:3}]}};
  const c={el,$:()=>root,api:async()=>data,query:()=>'',has:p=>p==='raw:read'&&rawPermission,
   intakeStatus:x=>x,reviewStatus:x=>x,evidenceStatus:x=>x,button:(label,action)=>el('button',label),list:async()=>{},Date};
  vm.createContext(c);vm.runInContext(FUNCTION,c);await c.showReport('test');return root.children;
 }
 const request=[{label:'상담 가능한 시간',text:'정정 원문 그대로: 목요일',status:'confirmed'}];
 console.log(JSON.stringify({complete:await render('complete',request,true),noRaw:await render('complete',request,false),expired:await render('complete',request,true,true),empty:await render('complete',[],true),progress:await render('in_progress',request,true)}));
})();
""".replace("FUNCTION", json.dumps(function)))

    def flatten(nodes):
        return [node.get("text", "") for node in nodes] + [text for node in nodes for text in flatten(node.get("children", []))]

    complete = result["complete"]
    sections = [(index, node["children"][0].get("text")) for index, node in enumerate(complete) if node.get("cls") == "report-section"]
    assert sections[0][1] == "접수 완료 때 반영한 추가 내용"
    assert sections[0][0] > next(i for i, node in enumerate(complete) if "사람 확인 필요" in node.get("text", ""))
    assert [title for _, title in sections].count("접수 완료 때 반영한 추가 내용") == 1
    assert "원문 그대로: 산책, 화요일" in flatten(complete)
    assert "정정 원문 그대로: 목요일" in flatten(complete)
    assert any("원문 출처도 함께" in text for text in flatten(complete))
    for name in ("noRaw", "expired"):
        assert not any("원문 출처도 함께" in text for text in flatten(result[name]))
        assert not any(text.startswith("원문 출처 #") for text in flatten(result[name]))
    for name in ("empty", "progress"):
        assert "접수 완료 때 반영한 추가 내용" not in flatten(result[name])
        assert "아직 접수 완료 때 반영한 추가 내용이 없습니다." in flatten(result[name])
    assert "정정 원문 그대로: 목요일" in flatten(result["progress"])
