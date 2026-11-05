"""Static UI contracts for the split institution/admin portal surfaces."""
from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "static" / "portal"


def source(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_shell_has_separate_mode_surfaces_and_testbed_warning():
    html = source("index.html")

    for marker in (
        'data-portal-mode="institution"',
        'id="admin-switch"',
        'id="institution-switch"',
        'id="admin-denied"',
        'id="institution-toolbar"',
        'id="registration-panel"',
        'id="testbed-panel"',
        'id="account-panel"',
    ):
        assert marker in html
    assert "합성 시험 자료만 사용합니다" in html
    assert "실제 기관의 접수 기록이나 내담자 자료를 복제하지 마세요" in html
    assert "관리번호는 TEST-로 시작합니다" in html


def test_admin_mode_is_fail_closed_and_institution_mode_hides_global_panels():
    script = source("app.js")

    assert 'const portalMode = document.body.dataset.portalMode === "admin" ? "admin" : "institution"' in script
    assert 'if (!isRegistrar)' in script
    assert '$("admin-denied").hidden = false' in script
    assert '$("registration-panel").hidden = true' in script
    assert '$("registration-panel").hidden = false' in script
    assert '$("layout").hidden = true' in script
    assert '$("link-panel").hidden = true' in script
    assert '$("member-panel").hidden = true' in script


def test_testbed_is_permission_scoped_and_uses_safe_synthetic_links():
    script = source("app.js")

    assert 'selectedPermissions.includes("report:read")' in script
    assert 'selectedPermissions.includes("link:issue")' in script
    assert 'api("/testbed","POST",{org_id:orgId})' in script
    assert 'result.synthetic!==true' in script
    assert '/^TEST-[A-Za-z0-9-]+$/' in script
    assert 'target.origin!==location.origin' in script
    assert 'link.rel="noopener noreferrer"' in script
    assert '"TESTBED 합성"' in script
    assert '"자료 구분: TESTBED 합성 자료"' in script


def test_login_return_and_current_device_revoke_are_mode_aware():
    script = source("app.js")

    assert 'return_to:portalMode === "admin" ? "/portal/admin" : "/portal"' in script
    assert 'new URLSearchParams(location.search).get("org_id")' in script
    assert 'd.current ? "이 기기 해제 후 로그아웃" : "기기 해제"' in script
    assert 'if (d.current || result.current_revoked)' in script
    assert '현재 기기를 해제해 로그아웃되었습니다' in script


def test_zero_membership_clears_institution_context_but_loads_devices():
    script = source("app.js")

    assert "function clearInstitutionContext()" in script
    assert 'org = ""; permissions = []; offset = 0; selected = null' in script
    assert 'for (const id of ["cases","metrics","links","members"]) $(id).replaceChildren()' in script
    assert '$("link-result").replaceChildren()' in script
    assert '$("layout").hidden = true; $("link-panel").hidden = true; $("member-panel").hidden = true' in script
    empty_branch = script[script.index("if (!me.organizations.length)"):script.index("await selectOrg();")]
    assert "clearInstitutionContext();" in empty_branch
    assert "await loadDevices();" in empty_branch


def test_unauthorized_clear_removes_sensitive_portal_dom():
    script = source("app.js")

    assert 'response.status === 401' in script
    for node_id in ("cases", "metrics", "links", "members", "devices", "registration-requests", "registration-users", "org-list", "testbed-result"):
        assert f'"{node_id}"' in script
    assert '$("report").replaceChildren' in script
    assert '$("link-result").replaceChildren()' in script
    assert 'for (const id of ["org","testbed-org","registration-org"]) $(id).replaceChildren()' in script


def test_institution_testbed_is_separate_from_global_admin():
    html, script = source("index.html"), source("app.js")
    assert 'id="institution-testbed-start"' in html
    assert '이 기관의 목록·집계·보고서에 포함됩니다' in html
    assert 'api("/institutions/testbed","POST",{org_id:orgId})' in script
    assert 'if(!has("link:issue")||!org) return' in script
    assert '$("institution-testbed-start").disabled = !has("link:issue")' in script
    assert '"institution-testbed-result"' in script[script.index("function clearWorkspace()"):script.index("const emailMode")]


def test_search_and_source_navigation_are_explicit():
    html, script = source("index.html"), source("app.js")
    assert 'id="search-status"' in html
    assert "검색한 관리번호와 일치하는 접수가 없습니다" in script
    assert "아직 접수된 내용이 없습니다" in script
    assert "검색 지우고 전체 목록 보기" in script
    assert "보고서 항목으로 돌아가기" in script
    assert "sourceOrigin.focus()" in script
    assert '<h2 id="account-title">기기 및 담당자 관리</h2><details>' in html
