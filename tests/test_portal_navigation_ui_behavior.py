"""Synthetic navigation regressions, without DB or browser credentials."""
import json
from pathlib import Path
import subprocess

SCRIPT = (Path(__file__).resolve().parents[1] / "static/portal/app.js").read_text()


def run(source, assertions):
    code = """
const vm = require('node:vm');
function node(tag='', text='') {
 return {tag,text,dataset:{},attributes:{},children:[],hidden:false,
  append(...items){this.children.push(...items)},
  prepend(...items){this.children.unshift(...items)},
  replaceChildren(...items){this.children=items},
  setAttribute(k,v){this.attributes[k]=v},
  focus(options){this.focused=options||true}};
}
const nodes = new Proxy({}, {get:(obj,id)=>obj[id]||(obj[id]=node())});
const c = {console,Date,Error,encodeURIComponent,document:{createElement:node},
 $:id=>nodes[id],el:node,button:(label,action)=>Object.assign(node('button',label),{action}),
 window:{scrollX:0,scrollY:840,scrollTo(x,y){this.restored={x,y}}},
 mobileLayout:{matches:true},contextVersion:0,listVersion:0,reportVersion:0,
 selected:null,reportOpen:false,listPosition:null,csrf:'synthetic',org:'a',
 query:()=>'?org_id=a',has:()=>false,returnToCases(){},
 intakeStatus:x=>x,reviewStatus:x=>x,evidenceStatus:x=>x,
 syncCaseView(){},notice(){},clearWorkspace(){c.cleared=true;c.contextVersion++},
 clearInstitutionContext(){c.denied=true;c.contextVersion++}};
vm.createContext(c);
vm.runInContext(SOURCE,c);
(async()=>{ ASSERTIONS })().catch(e=>{console.error(e);process.exitCode=1});
""".replace("SOURCE", json.dumps(source)).replace("ASSERTIONS", assertions)
    result = subprocess.run(["node", "-e", code], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def test_return_restores_same_selected_node_and_scroll_without_refetch():
    source = SCRIPT[SCRIPT.index("function syncCaseView()"):SCRIPT.index('mobileLayout.addEventListener')]
    result = run(source, """
const selected=node('button');selected.dataset.caseId='18';
nodes.cases.children=[selected];c.selected='18';c.reportOpen=true;c.listPosition={x:0,y:840};
c.returnToCases();
console.log(JSON.stringify({selected:c.selected,focus:selected.focused,
 listHidden:nodes['case-list'].hidden,reportHidden:nodes.report.hidden,
 restored:c.window.restored,rows:nodes.cases.children.length}));
""")
    assert result == {"selected": "18", "focus": {"preventScroll": True},
                      "listHidden": False, "reportHidden": True,
                      "restored": {"x": 0, "y": 840}, "rows": 1}


def test_latest_report_wins_when_responses_arrive_out_of_order():
    source = SCRIPT[SCRIPT.index("async function showReport("):SCRIPT.index('$("google-login").onclick')]
    result = run(source, """
const responses={};c.api=path=>new Promise(resolve=>responses[path]=resolve);
const a=c.showReport('1'),b=c.showReport('2');
const report=id=>({management_id:'TEST-'+id,status:'complete',updated_at:'2026-11-05',
 version:1,summary:{slots:{}},slot_labels:{},sources:{},reviews:[]});
responses['/intakes/2?org_id=a'](report('2'));await b;
responses['/intakes/1?org_id=a'](report('1'));await a;
console.log(JSON.stringify({selected:c.selected,heading:nodes.report.children[1].text,
 reportOpen:c.reportOpen,position:c.listPosition}));
""")
    assert result == {"selected": "2", "heading": "TEST-2 접수 보고서",
                      "reportOpen": True, "position": {"x": 0, "y": 840}}


def test_late_api_result_cannot_restore_previous_context():
    source = SCRIPT[SCRIPT.index("async function api("):SCRIPT.index("function clearWorkspace()")]
    result = run(source, """
let resolve;c.fetch=()=>new Promise(r=>resolve=r);
const pending=c.api('/intakes/26?org_id=a').catch(e=>e.message);
c.contextVersion++;
resolve({ok:true,json:async()=>({management_id:'TEST-26'})});
console.log(JSON.stringify({result:await pending,cleared:!!c.cleared}));
""")
    assert result == {"result": "stale-context", "cleared": False}


def test_context_reset_discards_report_selection_and_return_position():
    source = SCRIPT[SCRIPT.index("function syncCaseView()"):SCRIPT.index('mobileLayout.addEventListener')]
    result = run(source, """
c.selected='18';c.reportOpen=true;c.listPosition={x:0,y:840};
nodes.report.append(node('p','SYNTHETIC BODY'));
c.resetCaseView();
console.log(JSON.stringify({selected:c.selected,position:c.listPosition,reportOpen:c.reportOpen,
 report:nodes.report.children.map(x=>x.text),reportHidden:nodes.report.hidden,
 version:c.reportVersion}));
""")
    assert result == {"selected": None, "position": None, "reportOpen": False,
                      "report": ["접수 보고서"], "reportHidden": True, "version": 1}


def test_late_list_cannot_replace_newer_search_results():
    source = SCRIPT[SCRIPT.index("async function list()"):SCRIPT.index("async function showReport(")]
    result = run(source, """
const responses=[];c.offset=0;c.api=()=>new Promise(resolve=>responses.push(resolve));
nodes.search.value='';const first=c.list();
nodes.search.value='TEST-18';const filtered=c.list();
const item=id=>({id,management_id:'TEST-'+id,status:'complete',updated_at:'2026-11-05'});
responses[1]({items:[item('18')]});await filtered;
responses[0]({items:[item('1'),item('2')]});await first;
console.log(JSON.stringify({ids:nodes.cases.children.map(x=>x.dataset.caseId),
 status:nodes['search-status'].textContent,prev:nodes.prev.disabled,next:nodes.next.disabled}));
""")
    assert result == {"ids": ["18"], "status": "관리번호 ‘TEST-18’ 검색 결과",
                      "prev": True, "next": True}


def test_logout_success_is_not_discarded_when_institution_changes():
    source = SCRIPT[SCRIPT.index("async function api("):SCRIPT.index("function clearWorkspace()")]
    result = run(source, """
let resolve;c.fetch=()=>new Promise(r=>resolve=r);
const pending=c.api('/auth/logout','POST',{});
c.contextVersion++;
resolve({ok:true,json:async()=>({logged_out:true})});
console.log(JSON.stringify(await pending));
""")
    assert result == {"logged_out": True}
