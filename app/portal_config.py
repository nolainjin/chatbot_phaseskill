"""Provisional local policy. No production policy or external provider is selected."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Policy:
    device_seconds: int = 30 * 86400
    idle_seconds: int = 1800
    session_seconds: int = 8 * 3600
    email_session_seconds: int = 14 * 86400
    code_seconds: int = 600
    code_attempts: int = 5
    resend_seconds: int = 60
    sends_per_hour: int = 5
    link_seconds: int = 7 * 86400

    @classmethod
    def load(cls):
        values = {k: int(os.getenv('PORTAL_' + k.upper(), str(v.default)))
                  for k, v in cls.__dataclass_fields__.items()}
        if any(v <= 0 for v in values.values()):
            raise RuntimeError('Portal policy values must be positive')
        if values['email_session_seconds'] > 14 * 86400:
            raise RuntimeError('Email login sessions cannot exceed 14 days')
        return cls(**values)


def session_idle_seconds():
    policy = Policy.load()
    # Email sessions keep a fixed absolute deadline; activity never extends it.
    return policy.email_session_seconds if os.getenv('PORTAL_EMAIL_LOGIN') == '1' else policy.idle_seconds


def enabled():
    return os.getenv('PORTAL_ENABLED') == '1'


def local_only():
    # P5 adapters are intentionally not connected. Fail closed even if a flag is set remotely.
    return os.getenv('PORTAL_LOCAL_TEST') == '1' and not os.getenv('VERCEL')


def cloud():
    return os.getenv('PORTAL_AUTH_PROVIDER') == 'supabase' and os.getenv('PORTAL_LOCAL_TEST') != '1'


def validate_cloud():
    from urllib.parse import urlparse
    origin = urlparse(os.getenv('PORTAL_ORIGIN', ''))
    if (not cloud() or origin.scheme != 'https' or not origin.hostname
            or origin.path or origin.query or origin.fragment or origin.username or origin.port):
        raise RuntimeError('Cloud portal requires a fixed HTTPS origin')
    if os.getenv('SUPABASE_URL') != 'https://ojhuuipsyxewtiubujom.supabase.co':
        raise RuntimeError('Unexpected Supabase project')
    if not os.getenv('SUPABASE_PUBLISHABLE_KEY', '').startswith('sb_publishable_'):
        raise RuntimeError('Supabase publishable key is required')
    if len(os.getenv('PORTAL_CODE_SECRET', '')) < 32:
        raise RuntimeError('Stable portal secret is required')
