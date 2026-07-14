import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app import stats
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
    assert result["totals"]["notable_sessions"] == 1
    assert result["individual_flags"][0]["participant_id"] == "demo-person-001"
    assert result["individual_flags"][0]["flags"][0]["label"] == "지지체계 미확인"


def test_api_stats_returns_json(monkeypatch):
    monkeypatch.setattr(
        stats,
        "read_stats",
        lambda **_kwargs: {"totals": {"participants": 1}, "track_counts": []},
    )

    response = client.get("/api/stats")

    assert response.status_code == 200
    assert response.json()["totals"]["participants"] == 1
