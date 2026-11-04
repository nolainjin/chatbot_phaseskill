"""Real Claude smoke test with synthetic text and disposable local storage."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def hashes():
    return {str(p.relative_to(ROOT / 'data')): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / 'data').rglob('*') if p.is_file()}


def main():
    if not os.getenv('ANTHROPIC_API_KEY'):
        raise SystemExit('Run using claude_keychain.sh run; do not put the key in argv.')
    before = hashes()
    with tempfile.TemporaryDirectory(prefix='maeum-real-local-') as tmp:
        for key in list(os.environ):
            if key.startswith('PORTAL_') or key in ('MAEUM_DATABASE_URL', 'VERCEL', 'STATS_API_TOKEN'):
                os.environ.pop(key, None)
        os.environ.update(DATA_DIR=tmp, MODEL='claude-haiku-5-5', KNOWLEDGE_DIR=str(ROOT / 'knowledge-maeum'),
                          PRIVATE_LOCAL_UI='1', PUBLIC_CHAT_UI='0')
        from fastapi.testclient import TestClient
        from app.main import app
        from app import consent, storage, llm
        calls = []
        original = llm._ask_single_backend

        def counted(*args, **kwargs):
            value = original(*args, **kwargs)
            calls.append(args[0] if args else kwargs.get('model'))
            return value

        llm._ask_single_backend = counted
        with TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 51001)) as client:
            sid = 'real-local-' + uuid.uuid4().hex[:12]
            response = client.post('/api/consent', json={'session_id': sid, 'accepted': True,
                'consent_version': consent.load_privacy(str(ROOT / 'knowledge-maeum')).consent_version})
            assert response.status_code == 200, ('consent', response.status_code)
            accepted = response.json()
            credentials = {k: accepted[k] for k in ('session_token', 'participant_id', 'participant_ticket')}
            messages = ['회사 업무 때문에 불안하고 긴장돼요.',
                        '한 달 전부터 일이 많아져 잠들기 어렵고 출근할 때 집중이 잘 안 돼요.',
                        '지난달 팀이 바뀌면서 맡은 업무가 갑자기 늘어났어요.',
                        '퇴근 후 산책을 해봤어요.', '친한 친구가 이야기를 들어줘요.',
                        '상담에서 불안을 다루고 업무 부담을 조절하는 방법을 배우고 싶어요.', '없음, 이대로 보내기']
            for message in messages:
                response = client.post('/api/chat', json={'session_id': sid, **credentials, 'message': message})
                assert response.status_code == 200, ('chat', response.status_code)
                result = response.json()
                assert result.get('reply')
                print(json.dumps({'turn': result.get('turn'), 'reply': result['reply']}, ensure_ascii=False), flush=True)
            assert calls and all(model == 'claude-haiku-5-5' for model in calls)
            assert storage.conversation_exists(sid)
            docs = list(Path(tmp).glob('conversations/*/*.json'))
            snapshots = [json.loads(p.read_text()).get('intake_snapshot') for p in docs]
            assert snapshots and snapshots[0]['slots'].get('expectation') == messages[5], 'Expectation must reflect the actual answer'
            assert snapshots[0].get('handoff', {}).get('sent') is True
            print(json.dumps({'real_model_calls': len(calls), 'snapshots': snapshots}, ensure_ascii=False), flush=True)
            assert client.post('/api/chat', json={'session_id': sid, **credentials,
                'session_token': 'wrong', 'message': 'test'}).status_code == 401
            response = client.post('/api/session/delete', json={'delete_code': accepted['delete_code']})
            assert response.status_code == 200 and not storage.conversation_exists(sid)
    assert before == hashes()
    print('PASS: consent, real Claude, persisted conversation, ownership, deletion; original data unchanged.')


if __name__ == '__main__':
    main()
