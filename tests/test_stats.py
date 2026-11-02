import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app import stats, storage
from app.main import app

client = TestClient(app)


def _make_db(path: Path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE participants (participant_id TEXT PRIMARY KEY);
        CREATE TABLE conversations (
            date TEXT NOT NULL,
            session_id TEXT NOT NULL,
            participant_id TEXT NOT NULL,
            PRIMARY KEY (date, session_id)
        );
        CREATE TABLE turns (
            date TEXT NOT NULL,
            session_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            role TEXT NOT NULL,
            text TEXT NOT NULL,
            PRIMARY KEY (date, session_id, seq)
        );
        """
    )
    conn.execute("INSERT INTO participants VALUES ('demo-person-001')")
    conn.execute("INSERT INTO conversations VALUES ('2026-07-14','demo-session-001','demo-person-001')")
    conn.execute("INSERT INTO turns VALUES ('2026-07-14','demo-session-001',0,'user','우울해서 잠을 못 자요')")
    conn.execute("INSERT INTO turns VALUES ('2026-07-14','demo-session-001',1,'assistant','언제부터였나요?')")
    conn.execute(
        "INSERT INTO turns VALUES ('2026-07-14','demo-session-001',2,'intake_summary',?)",
        (
            json.dumps(
                {
                    "track": "정서",
                    "slots": {"track": "정서", "chief_complaint": "우울해서 잠을 못 자요"},
                    "unfilled": {"support": "미확인"},
                    "red_flags": [],
                },
                ensure_ascii=False,
            ),
        ),
    )
    conn.commit()
    conn.close()


def test_read_stats_returns_dashboard_shape(tmp_path):
    db_path = tmp_path / "chatlog.db"
    _make_db(db_path)

    result = stats.read_stats(db_path)

    assert result["totals"]["participants"] == 1
    assert result["totals"]["conversations"] == 1
    assert result["track_counts"] == [{"track": "정서", "count": 1}]
    assert result["slot_completion"][0]["completed"] >= 1
    assert result["recent_sessions"][0]["participant_id"] == "demo-person-001"
    assert result["recent_sessions"][0]["chief_complaint"] == "[recorded]"
    assert result["recent_sessions"][0]["summary_available"] is True
    assert "지지체계" in result["recent_sessions"][0]["missing"]
    assert result["totals"]["notable_sessions"] == 1
    assert result["individual_flags"][0]["participant_id"] == "demo-person-001"
    assert result["individual_flags"][0]["flags"][0]["label"] == "지지체계 미확인"


def test_read_session_detail_returns_ordered_conversation(tmp_path):
    db_path = tmp_path / "chatlog.db"
    _make_db(db_path)

    detail = stats.read_session_detail(
        "2026-07-14",
        "demo-session-001",
        db_path,
    )

    assert detail is not None
    assert detail["participant_id"] == "demo-person-001"
    assert [turn["seq"] for turn in detail["turns"]] == [0, 1, 2]
    assert detail["turns"][0]["role"] == "user"
    assert detail["turns"][0]["text"] == "우울해서 잠을 못 자요"


def test_addiction_handoff_is_flagged_without_false_missing_support():
    record = stats._individual_flag_record(
        "2026-07-14",
        "addiction-session",
        "addiction-person",
        {
            "track": "중독",
            "slots": {
                "track": "중독",
                "chief_complaint": "도박 빚이 생겼어요",
                "addiction_type": "도박",
                "addiction_severity": "고위험",
                "addiction_referral": "전문기관 정보 제공",
            },
            "unfilled": {},
            "red_flags": [],
        },
        user_turns=1,
    )

    assert record is not None
    assert record["severity"] == "medium"
    assert [flag["label"] for flag in record["flags"]] == ["중독 전문기관 우선"]
    assert record["missing"] == []
    assert record["addiction_type"] == "도박"
    assert record["addiction_severity"] == "고위험"
    assert record["addiction_referral"] == "전문기관 정보 제공"


def test_sync_today_makes_current_json_visible(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    storage.append_turn(
        "managed-session",
        "user",
        "상담을 신청합니다.",
        participant_id="BX-2026-001",
    )

    assert stats.sync_today() == 1
    result = stats.read_stats()

    assert result["recent_sessions"][0]["participant_id"] == "BX-2026-001"

def test_api_stats_returns_json(monkeypatch):
    monkeypatch.setenv("STATS_API_TOKEN", "stats-test-token")
    monkeypatch.setattr(stats, "sync_today", lambda: 0)
    monkeypatch.setattr(
        stats,
        "read_stats",
        lambda **_kwargs: {"totals": {"participants": 1}, "track_counts": []},
    )

    response = client.get("/api/stats", headers={"X-Stats-Token": "stats-test-token"})

    assert response.status_code == 200
    assert response.json()["totals"]["participants"] == 1


def test_api_stats_rejects_anonymous_requests(monkeypatch):
    monkeypatch.setenv("STATS_API_TOKEN", "stats-test-token")

    response = client.get("/api/stats")

    assert response.status_code == 401


def test_loopback_dashboard_bootstraps_httponly_admin_session(monkeypatch):
    monkeypatch.setenv("STATS_API_TOKEN", "stats-test-token")
    monkeypatch.setattr(stats, "sync_today", lambda: 0)
    monkeypatch.setattr(
        stats,
        "read_stats",
        lambda **_kwargs: {"totals": {"participants": 1}, "track_counts": []},
    )
    local_client = TestClient(app)

    dashboard = local_client.get("/stats.html")
    assert dashboard.status_code == 200
    assert "httponly" in dashboard.headers["set-cookie"].lower()
    assert "samesite=strict" in dashboard.headers["set-cookie"].lower()

    response = local_client.get("/api/stats")
    assert response.status_code == 200
    assert response.json()["totals"]["participants"] == 1


def test_api_stats_session_requires_auth_and_returns_detail(monkeypatch):
    monkeypatch.setenv("STATS_API_TOKEN", "stats-test-token")
    monkeypatch.setattr(stats, "sync_today", lambda: 0)
    monkeypatch.setattr(
        stats,
        "read_session_detail",
        lambda day, session_id: {
            "date": day,
            "session_id": session_id,
            "participant_id": "BX-2026-001",
            "turns": [{"seq": 0, "role": "user", "text": "상담을 신청합니다."}],
        },
    )

    anonymous = TestClient(app).get(
        "/api/stats/session",
        params={"day": "2026-07-14", "session_id": "managed-session"},
    )
    assert anonymous.status_code == 401

    response = TestClient(app).get(
        "/api/stats/session",
        params={"day": "2026-07-14", "session_id": "managed-session"},
        headers={"X-Stats-Token": "stats-test-token"},
    )
    assert response.status_code == 200
    assert response.json()["participant_id"] == "BX-2026-001"
    assert response.json()["turns"][0]["text"] == "상담을 신청합니다."
