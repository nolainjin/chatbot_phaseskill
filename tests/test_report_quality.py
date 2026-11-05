from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app import portal_store, report_quality


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/report-quality-legacy.json"


def _target():
    fixture = json.loads(FIXTURE.read_text())
    return {"summary": fixture["summary"], "sources": fixture["sources"]}, fixture["documents"]


def test_target_projection_is_grounded_and_does_not_mutate_source_fixture():
    report, documents = _target()
    before_report, before_documents = deepcopy(report), deepcopy(documents)

    result = report_quality.project(report["summary"], report["sources"], documents)

    assert report == before_report and documents == before_documents
    summary, sources = result["summary"], result["sources"]
    assert summary["track"] == summary["slots"]["track"] == "정서"
    assert summary["track_inferred"] is True
    assert "relationship_target" not in summary["slots"]
    assert "relationship_duration" not in summary["slots"]
    assert summary["slot_evidence"]["support"] == {"status": "unconfirmed"}
    assert summary["slot_evidence"]["expectation"] == {"status": "unconfirmed"}
    assert summary["unfilled"]["support"] == "미확인"
    assert summary["unfilled"]["expectation"] == "미확인"
    assert summary["slots"]["symptom_context"] == (
        "한 석달전부터? 중간고사 이후부터요. / 저녁에 책상에 앉으면요"
    )
    assert sources["symptom_context"] == [
        {"day": "2026-11-05", "seq": 6, "role": "user"},
        {"day": "2026-11-05", "seq": 12, "role": "user"},
    ]
    assert not {"support", "expectation", "relationship_target", "relationship_duration"} & sources.keys()
    quality = summary["report_quality"]
    assert quality["algorithm_version"] == report_quality.ALGORITHM_VERSION
    assert all(set(item) == {"field", "reason"} for item in quality["repairs"])


def test_valid_support_expectation_and_real_relationship_are_preserved():
    documents = [{"day": "2026-11-05", "turns": [
        {"seq": 0, "role": "assistant", "text": "이 이야기를 알고 있거나 곁에서 도와주는 사람이 있나요?"},
        {"seq": 1, "role": "user", "text": "없어요"},
        {"seq": 2, "role": "assistant", "text": "이번 상담에서 어떤 도움을 가장 기대하시나요?"},
        {"seq": 3, "role": "user", "text": "잘 모르겠어요"},
        {"seq": 4, "role": "user", "text": "친구와 싸운 뒤 공부에 집중이 안 돼요"},
    ]}]
    summary = {"track": "관계", "track_inferred": True, "slots": {
        "track": "관계", "support": "없어요", "expectation": "잘 모르겠어요",
        "relationship_target": "친구",
    }, "slot_evidence": {}, "unfilled": {}}
    sources = {
        "support": [{"day": "2026-11-05", "seq": 1, "role": "user"}],
        "expectation": [{"day": "2026-11-05", "seq": 3, "role": "user"}],
    }

    result = report_quality.project(summary, sources, documents)

    assert result["summary"]["slots"]["support"] == "없어요"
    assert result["summary"]["slots"]["expectation"] == "잘 모르겠어요"
    assert result["summary"]["track"] == "관계"
    assert "report_quality" not in result["summary"]


def test_later_friend_conflict_preserves_relationship_even_with_academic_comparison_source():
    summary = {"track": "관계", "track_inferred": True, "slots": {
        "track": "관계", "relationship_target": "친구",
    }, "slot_evidence": {}, "unfilled": {}}
    sources = {"track": [{"day": "2026-11-05", "seq": 4, "role": "user"}]}
    documents = [{"day": "2026-11-05", "turns": [
        {"seq": 0, "role": "user", "text": "공부에 집중하기 힘들어요"},
        {"seq": 4, "role": "user", "text": "친구들에게 따라잡힐까 걱정돼요"},
        {"seq": 5, "role": "user", "text": "그 친구랑 자주 싸웠고 따돌림도 있었어요"},
    ]}]

    result = report_quality.project(summary, sources, documents)

    assert result["summary"] == summary
    assert result["sources"] == sources


def test_academic_words_do_not_hide_source_grounded_peer_harm():
    summary = {"track": "관계", "track_inferred": True, "slots": {
        "track": "관계", "relationship_target": "친구",
    }, "slot_evidence": {}, "unfilled": {}}
    sources = {"track": [{"day": "2026-11-05", "seq": 1, "role": "user"}]}
    documents = [{"day": "2026-11-05", "turns": [
        {"seq": 1, "role": "user", "text": "친구가 시험 성적을 비교하며 조롱해서 불안해요"},
    ]}]

    assert report_quality.project(summary, sources, documents) == {
        "summary": summary, "sources": sources,
    }


def test_unrecognized_but_plausible_expectation_question_is_not_reclassified():
    summary = {"track": "정서", "slots": {
        "track": "정서", "expectation": "차분해지는 거요",
    }, "slot_evidence": {}, "unfilled": {}}
    sources = {"expectation": [{"day": "2026-11-05", "seq": 2, "role": "user"}]}
    documents = [{"day": "2026-11-05", "turns": [
        {"seq": 1, "role": "assistant", "text": "상담을 받고 난 뒤 어떤 변화를 바라세요?"},
        {"seq": 2, "role": "user", "text": "차분해지는 거요"},
    ]}]

    assert report_quality.project(summary, sources, documents) == {
        "summary": summary, "sources": sources,
    }


def test_summary_only_study_help_is_preserved_as_support():
    summary = {"track": "정서", "slots": {
        "track": "정서", "support": "친구가 공부를 같이 해줘요",
    }, "slot_evidence": {}, "unfilled": {}}
    sources = {"support": [{"day": "2026-11-05", "seq": 2, "role": "user"}]}

    assert report_quality.project(summary, sources, None) == {
        "summary": summary, "sources": sources,
    }


@pytest.mark.parametrize("source,extra_turns", [
    ({"day": "2026-11-05", "seq": 3, "role": "user"}, []),
    ({"day": "2026-11-05", "seq": 1, "role": "user"}, []),
    ({"day": "2026-11-05", "seq": True, "role": "user"}, []),
    ({"day": "2026-11-05", "seq": 2, "role": "user"}, [
        {"seq": 2, "role": "assistant", "text": "duplicate sequence"},
    ]),
])
def test_invalid_explicit_sources_never_reassign_timing(source, extra_turns):
    summary = {"track": "정서", "slots": {
        "track": "정서", "expectation": "저녁에 책상에 앉으면요",
    }, "slot_evidence": {}, "unfilled": {}}
    sources = {"expectation": [source]}
    documents = [{"day": "2026-11-05", "turns": [
        {"seq": 1, "role": "assistant", "text": "이 생각들이 주로 언제 올라오나요?"},
        {"seq": 2, "role": "user", "text": "저녁에 책상에 앉으면요"},
        {"seq": 3, "role": "user", "text": "전혀 다른 말이에요"},
        *extra_turns,
    ]}]

    assert report_quality.project(summary, sources, documents) == {
        "summary": summary, "sources": sources,
    }


def test_exact_text_fallback_rejects_duplicate_day_and_sequence():
    summary = {"track": "정서", "slots": {
        "track": "정서", "expectation": "저녁에 책상에 앉으면요",
    }, "slot_evidence": {}, "unfilled": {}}
    documents = [{"day": "2026-11-05", "turns": [
        {"seq": 1, "role": "assistant", "text": "이 생각들이 주로 언제 올라오나요?"},
        {"seq": 2, "role": "user", "text": "저녁에 책상에 앉으면요"},
        {"seq": 2, "role": "assistant", "text": "duplicate sequence"},
    ]}]

    assert report_quality.project(summary, {}, documents) == {
        "summary": summary, "sources": {},
    }


def test_multiple_track_sources_cannot_fall_back_to_single_evidence_pointer():
    summary = {"track": "관계", "track_inferred": True, "slots": {
        "track": "관계", "relationship_target": "친구",
    }, "slot_evidence": {
        "track": {"status": "answered", "value": "관계",
                  "source": {"day": "2026-11-05", "seq": 2, "role": "user"}},
    }, "unfilled": {}}
    sources = {"track": [
        {"day": "2026-11-05", "seq": 2, "role": "user"},
        {"day": "2026-11-05", "seq": 3, "role": "user"},
    ]}
    documents = [{"day": "2026-11-05", "turns": [
        {"seq": 0, "role": "user", "text": "공부에 집중하기 힘들어요"},
        {"seq": 2, "role": "user", "text": "친구들에게 따라잡힐까 걱정돼요"},
        {"seq": 3, "role": "user", "text": "비슷한 생각이 들어요"},
    ]}]

    assert report_quality.project(summary, sources, documents) == {
        "summary": summary, "sources": sources,
    }


def test_day_is_required_to_resolve_repeated_sequence_numbers():
    summary = {"track": "정서", "slots": {"track": "정서", "expectation": "저녁에 책상에 앉으면요"},
               "slot_evidence": {}, "unfilled": {}}
    documents = [
        {"day": "2026-11-04", "turns": [
            {"seq": 1, "role": "assistant", "text": "이번 상담에서 어떤 도움을 가장 기대하시나요?"},
            {"seq": 2, "role": "user", "text": "저녁에 책상에 앉으면요"},
        ]},
        {"day": "2026-11-05", "turns": [
            {"seq": 1, "role": "assistant", "text": "이 생각들이 주로 언제 올라오나요?"},
            {"seq": 2, "role": "user", "text": "저녁에 책상에 앉으면요"},
        ]},
    ]
    sources = {"expectation": [{"day": "2026-11-05", "seq": 2, "role": "user"}]}

    result = report_quality.project(summary, sources, documents)

    assert result["sources"]["symptom_context"] == [
        {"day": "2026-11-05", "seq": 2, "role": "user"}
    ]
    assert result["summary"]["slots"]["symptom_context"] == "저녁에 책상에 앉으면요"


def test_ambiguous_source_is_not_reassigned():
    summary = {"track": "정서", "slots": {"track": "정서", "expectation": "저녁에 책상에 앉으면요"},
               "slot_evidence": {}, "unfilled": {}}
    documents = [
        {"day": day, "turns": [
            {"seq": 0, "role": "assistant", "text": "이 생각들이 주로 언제 올라오나요?"},
            {"seq": 1, "role": "user", "text": "저녁에 책상에 앉으면요"},
        ]}
        for day in ("2026-11-04", "2026-11-05")
    ]

    result = report_quality.project(summary, {}, documents)

    assert result["summary"] == summary
    assert result["sources"] == {}


class _Result:
    def __init__(self, *, one=None, many=None):
        self.one = one
        self.many = many or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class _Conn:
    def __init__(self, row, permitted=False, documents=None):
        self.row = deepcopy(row)
        self.permitted = permitted
        self.documents = documents or []
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append(query)
        if "FROM maeum.intakes i JOIN maeum.report_snapshots" in query:
            return _Result(one=deepcopy(self.row))
        if "maeum.permitted" in query:
            return _Result(one={"ok": self.permitted})
        if "maeum.read_transcript" in query:
            return _Result(many=[{"document": deepcopy(item)} for item in self.documents])
        if "FROM maeum.portal_reviews" in query:
            return _Result(many=[])
        raise AssertionError(query)


def _row():
    return {"id": "i", "management_id": "m", "summary": {
        "track": "정서", "slots": {"track": "정서", "expectation": "저녁에 책상에 앉으면요"},
        "slot_evidence": {"expectation": {"source_text": "raw"}}, "unfilled": {},
    }, "version": 1, "source_revision": "r", "status": "complete", "raw_expired": False,
            "sources": {"expectation": [{"day": "2026-11-05", "seq": 2}]}}


def test_summary_only_never_reads_transcript_and_foreign_row_stops_first():
    conn = _Conn(_row(), permitted=False)
    result = portal_store.detail(conn, "A", "i")
    assert not any("read_transcript" in query for query in conn.queries)
    assert result["summary"]["slot_evidence"]["expectation"] == {"status": "unconfirmed"}

    missing = _Conn(None, permitted=True)
    with pytest.raises(HTTPException) as error:
        portal_store.detail(missing, "A", "foreign")
    assert error.value.status_code == 404
    assert not any("permitted" in query or "read_transcript" in query for query in missing.queries)


def test_purged_document_stops_projection_and_scrubs_legacy_provenance():
    document = {"day": "2026-11-05", "raw_purged_at": "2026-12-01", "turns": []}
    conn = _Conn(_row(), permitted=True, documents=[document])

    result = portal_store.detail(conn, "A", "i")

    assert result["raw_expired"] is True
    assert result["sources"] == {}
    assert "slot_evidence" not in result["summary"]
    assert "report_quality" not in result["summary"]
    direct = report_quality.project(_row()["summary"], _row()["sources"], [document])
    assert direct == {"summary": _row()["summary"], "sources": _row()["sources"]}
