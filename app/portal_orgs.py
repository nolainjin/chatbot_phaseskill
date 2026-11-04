"""Registrar-managed institutions. Writes go through SECURITY DEFINER functions."""
from fastapi import HTTPException
import psycopg

from app import portal_auth as auth
from app.portal_email import registrar

NAME_ERROR = '기관 이름을 1~80자로 입력해 주세요.'
_ERRORS = {
    'invalid organization name': (400, NAME_ERROR),
    'duplicate organization': (409, '같은 이름의 기관이 이미 있습니다.'),
    'organization not found': (404, '기관을 찾을 수 없습니다.'),
    'registrar required': (403, '이메일 등록 관리자만 이용할 수 있습니다.'),
}


def clean_name(value):
    if not isinstance(value, str):
        raise HTTPException(400, NAME_ERROR)
    value = value.strip()
    if not 1 <= len(value) <= 80:
        raise HTTPException(400, NAME_ERROR)
    return value


def translate(exc):
    status, text = _ERRORS.get(exc.diag.message_primary, (None, None))
    if not status:
        raise exc
    raise HTTPException(status, text) from exc


def directory(request):
    with auth.connect() as conn:
        row = registrar(conn, request)
        return {'organizations': conn.execute('SELECT maeum.org_directory(%s) AS document', (row['token_hash'],)).fetchone()['document']}


def create(request, payload):
    name = payload.get('name')
    with auth.connect() as conn:
        row = registrar(conn, request)
        name = clean_name(name)
        try:
            return {'id': conn.execute('SELECT maeum.create_organization(%s,%s) AS id', (row['token_hash'], name)).fetchone()['id']}
        except psycopg.errors.RaiseException as exc:
            translate(exc)


def update(request, org_id, payload):
    name, active = payload.get('name'), payload.get('active')
    with auth.connect() as conn:
        row = registrar(conn, request)
        name = clean_name(name)
        if type(active) is not bool:
            raise HTTPException(400, '활성 상태를 확인해 주세요.')
        try:
            conn.execute('SELECT maeum.update_organization(%s,%s,%s,%s)', (row['token_hash'], org_id, name, active))
        except psycopg.errors.RaiseException as exc:
            translate(exc)
    return {'updated': True}
