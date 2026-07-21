from __future__ import annotations

import os
import time
from typing import Final

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from app import chat, storage
from app.config import Settings
from app.voice_boundary import (
    declared_body_too_large,
    is_loopback_client,
    parsed_multipart_payload_too_large,
    prepare_transcription_audio,
)
from app.voice_contracts import (
    MAX_AUDIO_BYTES,
    MAX_AUDIO_DURATION_MS,
    MAX_TTS_CHARS,
    MIN_AUDIO_DURATION_MS,
    AudioDecodeError,
    SynthesisProvider,
    SynthesizeRequest,
    TranscriptionProvider,
    TranscriptionProviderOutput,
    TranscriptionResponse,
    UnavailableSynthesisProvider,
    UnavailableTranscriptionProvider,
    VoiceErrorCode,
    VoiceErrorResponse,
    VoiceProviderError,
    validate_synthesized_audio,
)

VOICE_HTTP_STATUS: Final = 503

router = APIRouter(prefix="/api/voice", tags=["voice"])
transcription_provider: TranscriptionProvider = UnavailableTranscriptionProvider()
synthesis_provider: SynthesisProvider = UnavailableSynthesisProvider()


def _error(code: VoiceErrorCode, status_code: int, detail: str) -> JSONResponse:
    body = VoiceErrorResponse(error_code=code, detail=detail)
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def _voice_enabled() -> bool:
    return Settings.from_env().voice_enabled


def _require_local(request: Request) -> JSONResponse | None:
    host = request.client.host if request.client is not None else None
    if is_loopback_client(host):
        return None
    return _error(
        VoiceErrorCode.LOCAL_ONLY_VIOLATION,
        403,
        "음성 API는 로컬 요청만 허용합니다.",
    )


def _validate_session_metadata(
    session_id: str,
    session_token: str | None,
    participant_id: str | None,
) -> JSONResponse | None:
    if not storage.valid_session_id(session_id):
        return _error(
            VoiceErrorCode.INVALID_REQUEST, 400, "session_id 형식이 올바르지 않습니다."
        )
    if participant_id is not None and not storage.valid_participant_id(participant_id):
        return _error(
            VoiceErrorCode.INVALID_REQUEST,
            400,
            "participant_id 형식이 올바르지 않습니다.",
        )
    if session_token is not None and len(session_token) > 128:
        return _error(
            VoiceErrorCode.INVALID_REQUEST,
            400,
            "session_token 형식이 올바르지 않습니다.",
        )
    if chat.has_session(session_id) and not chat.owns_session(session_id, session_token):
        return _error(
            VoiceErrorCode.SESSION_AUTH_REQUIRED,
            401,
            "세션 인증이 필요합니다.",
        )
    if not chat.has_session(session_id) and storage.conversation_exists(session_id):
        return _error(
            VoiceErrorCode.SESSION_AUTH_REQUIRED,
            401,
            "세션 인증이 필요합니다.",
        )
    return None


@router.post("/transcribe", response_model=None)
async def transcribe(
    request: Request,
) -> Response | TranscriptionResponse:
    local_error = _require_local(request)
    if local_error is not None:
        return local_error
    if not _voice_enabled():
        return _error(
            VoiceErrorCode.VOICE_DISABLED,
            VOICE_HTTP_STATUS,
            "음성 기능이 비활성화되어 있습니다.",
        )
    if declared_body_too_large(request.headers.get("content-length")):
        return _error(
            VoiceErrorCode.AUDIO_TOO_LARGE, 413, "오디오가 10 MiB를 초과합니다."
        )
    form = await request.form()
    try:
        if parsed_multipart_payload_too_large(form):
            return _error(
                VoiceErrorCode.AUDIO_TOO_LARGE, 413, "오디오가 10 MiB를 초과합니다."
            )
        session_id_value = form.get("session_id")
        session_token_value = form.get("session_token")
        participant_id_value = form.get("participant_id")
        audio_value = form.get("audio")
        session_id = session_id_value if isinstance(session_id_value, str) else None
        session_token = session_token_value if isinstance(session_token_value, str) else None
        participant_id = (
            participant_id_value if isinstance(participant_id_value, str) else None
        )
        audio = audio_value if isinstance(audio_value, UploadFile) else None
        if session_id is None or audio is None:
            return _error(
                VoiceErrorCode.INVALID_REQUEST,
                400,
                "session_id와 audio가 필요합니다.",
            )
        metadata_error = _validate_session_metadata(
            session_id, session_token, participant_id
        )
        if metadata_error is not None:
            return metadata_error
        payload = await audio.read(MAX_AUDIO_BYTES + 1)
        if len(payload) > MAX_AUDIO_BYTES:
            return _error(
                VoiceErrorCode.AUDIO_TOO_LARGE, 413, "오디오가 10 MiB를 초과합니다."
            )
        if not payload:
            return _error(VoiceErrorCode.INVALID_AUDIO, 400, "오디오가 비어 있습니다.")
        try:
            prepared = await anyio.to_thread.run_sync(
                prepare_transcription_audio,
                payload,
                audio.content_type,
                os.getenv("VOICE_FFMPEG_BIN", "ffmpeg"),
            )
        except AudioDecodeError:
            return _error(
                VoiceErrorCode.INVALID_AUDIO, 400, "지원하지 않는 오디오 형식입니다."
            )
        if prepared.duration_ms < MIN_AUDIO_DURATION_MS:
            return _error(
                VoiceErrorCode.AUDIO_TOO_SHORT, 400, "오디오는 800ms 이상이어야 합니다."
            )
        if prepared.duration_ms > MAX_AUDIO_DURATION_MS:
            return _error(
                VoiceErrorCode.AUDIO_TOO_LONG, 400, "오디오는 60초 이하여야 합니다."
            )
        started = time.perf_counter()
        try:
            raw_provider_output = await anyio.to_thread.run_sync(
                transcription_provider.transcribe,
                prepared.content,
                prepared.content_type,
            )
        except AudioDecodeError:
            return _error(
                VoiceErrorCode.INVALID_AUDIO,
                400,
                "오디오를 디코드할 수 없습니다.",
            )
        except VoiceProviderError as exc:
            return _error(
                exc.error_code,
                VOICE_HTTP_STATUS,
                "로컬 음성 provider를 사용할 수 없습니다.",
            )
        try:
            provider_output = TranscriptionProviderOutput.model_validate(raw_provider_output)
            provider_output = provider_output.model_copy(
                update={"text": provider_output.text.strip()}
            )
            result = TranscriptionResponse(
                text=provider_output.text,
                language=provider_output.language,
                duration_ms=prepared.duration_ms,
                model=provider_output.model,
                provider=provider_output.provider,
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
        except ValidationError:
            return _error(
                VoiceErrorCode.PROVIDER_UNAVAILABLE,
                VOICE_HTTP_STATUS,
                "provider 전사 결과가 올바르지 않습니다.",
            )
        return result
    finally:
        await form.close()


@router.post("/synthesize", response_model=None)
def synthesize(request: Request, payload: SynthesizeRequest) -> Response:
    local_error = _require_local(request)
    if local_error is not None:
        return local_error
    if not _voice_enabled():
        return _error(
            VoiceErrorCode.VOICE_DISABLED,
            VOICE_HTTP_STATUS,
            "음성 기능이 비활성화되어 있습니다.",
        )
    if not payload.text.strip() or len(payload.text) > MAX_TTS_CHARS:
        return _error(
            VoiceErrorCode.INVALID_TEXT,
            400,
            "TTS 텍스트는 1~1200자여야 합니다.",
        )
    if payload.session_id is not None:
        metadata_error = _validate_session_metadata(payload.session_id, payload.session_token, None)
        if metadata_error is not None:
            return metadata_error
    try:
        predicted_duration_ms = synthesis_provider.predict_duration_ms(payload.text)
    except VoiceProviderError as exc:
        return _error(
            exc.error_code,
            VOICE_HTTP_STATUS,
            "로컬 음성 provider를 사용할 수 없습니다.",
        )
    if predicted_duration_ms > MAX_AUDIO_DURATION_MS:
        return _error(
            VoiceErrorCode.AUDIO_TOO_LONG, 400, "예상 TTS 길이가 60초를 초과합니다."
        )
    try:
        audio = synthesis_provider.synthesize(payload.text)
    except VoiceProviderError as exc:
        return _error(
            exc.error_code,
            VOICE_HTTP_STATUS,
            "로컬 음성 provider를 사용할 수 없습니다.",
        )
    if not validate_synthesized_audio(audio):
        return _error(
            VoiceErrorCode.PROVIDER_UNAVAILABLE,
            VOICE_HTTP_STATUS,
            "provider audio output이 올바르지 않습니다.",
        )
    return Response(
        content=audio.content,
        media_type=audio.media_type,
        headers={"Cache-Control": "no-store", "X-Voice-Duration-Ms": str(audio.duration_ms)},
    )
