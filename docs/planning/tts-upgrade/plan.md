# TTS 업그레이드 구현 계획 — Supertonic 3 + Fish-Speech

작성일: 2026-07-22 · 상태: **검토 대기 (승인 전 구현 금지)**
전제 리서치: [research.md](./research.md)

## 확정 사항
- Yuna(macOS say)는 스위치로 유지하다가 **최종 확정 후 제거**.
- **Supertonic 3 = 상시 운영 후보**(상업 배포 대비), **Fish-Speech = A/B 비교용 실험**(비상업).
- 백엔드는 `VOICE_TTS_PROVIDER` 환경변수로 전환: `macos-say` | `supertonic` | `fish-speech`.
- 프론트(`static/tts.js`)·API 계약·샘플레이트 검증은 **변경 불필요**(WAV bytes 그대로 수용).

---

## 마일스톤

### M1 — Supertonic 3 통합 (핵심)
1. **의존성 설치** (`.voice-venv`)
   ```bash
   .voice-venv/bin/pip install supertonic onnxruntime
   ```
   - ⚠️ 리스크: 기존 mlx(STT)와 numpy/onnxruntime 버전 충돌 가능 → 설치 후 `import mlx_audio, mlx_whisper; import supertonic` 동시 임포트 스모크로 검증. 충돌 시 별도 venv(`.tts-venv`) 분리 대안.

2. **모델 사전 다운로드** (네트워크 차단 정책과 분리)
   ```bash
   .voice-venv/bin/python -c "from supertonic import TTS; TTS(auto_download=True)"
   # ~400MB → ~/.cache/supertonic3/ (이후 완전 오프라인)
   ```
   - 런처의 `VOICE_NETWORK_DENY=1`은 STT 경로용. TTS 최초 다운로드는 이 사전 단계에서만 수행, 이후 `auto_download=False`.

3. **백엔드 구현** — `voice_runtime/adapters.py`에 추가 (MacSayBackend와 동일 계약)
   ```python
   class SupertonicTtsBackend:
       def __init__(self, voice_name: str = "F1") -> None:
           self.voice_name = voice_name
           self._tts = None
       def synthesize(self, text: str) -> bytes:
           if self._tts is None:
               try:
                   from supertonic import TTS
                   self._tts = TTS(auto_download=False)  # 오프라인
               except (ImportError, OSError, RuntimeError) as exc:
                   raise RuntimeProviderUnavailable from exc
           try:
               style = self._tts.get_voice_style(voice_name=self.voice_name)
               with tempfile.TemporaryDirectory(prefix="voice-tts-") as d:
                   wav, _ = self._tts.synthesize(text, voice_style=style, lang="ko")
                   out = Path(d) / "speech.wav"
                   self._tts.save_audio(wav, str(out))     # 44.1kHz 16bit WAV
                   content = out.read_bytes()
           except (OSError, RuntimeError, ValueError) as exc:
               raise RuntimeProviderUnavailable from exc
           try:
               return validate_wav_bytes(content).content
           except RuntimeAudioError as exc:
               raise RuntimeProviderUnavailable from exc
   ```
   - 지연 로딩(첫 합성 시 모델 로드) — MacSayBackend 패턴과 일관. 임시파일 방식도 동일(검증 로직 재사용).

4. **프로바이더 분기** — `build_backends()` 수정
   ```python
   def _build_tts() -> tuple[TtsBackend, str]:
       provider = os.getenv("VOICE_TTS_PROVIDER", "macos-say")
       match provider:
           case "supertonic":
               return SupertonicTtsBackend(os.getenv("VOICE_SUPERTONIC_VOICE", "F1")), \
                      f"supertonic-3:{os.getenv('VOICE_SUPERTONIC_VOICE', 'F1')}"
           case "fish-speech":
               return FishSpeechTtsBackend(...), "fish-speech"   # M2에서 구현
           case _:
               return MacSayBackend(os.getenv("VOICE_TTS_VOICE", "Yuna")), \
                      f"macos-say:{os.getenv('VOICE_TTS_VOICE', 'Yuna')}"
   # build_backends 반환부: stt, tts, model, tts_name = ... ; return stt, tts, model, tts_name
   ```

5. **설정/런처 노출**
   - `app/config.py`: `voice_tts_model`을 `VOICE_TTS_PROVIDER`에 따라 표기(`supertonic-3:F1` 등).
   - `scripts/run_local_voice.py`: `os.environ.setdefault("VOICE_TTS_PROVIDER", "macos-say")` + CLI `--tts {macos-say,supertonic,fish-speech}` 플래그.

6. **검증(A/B)**
   - `VOICE_TTS_PROVIDER=supertonic`으로 서버 기동 → `/api/config` `voice.tts`가 `supertonic-3:F1` 확인.
   - 백엔드 직접 스모크: 동일 한국어 문장을 Yuna/Supertonic으로 각각 합성해 WAV 저장·청취 비교.
   - 브라우저 음성 왕복(녹음→전사→답변→Supertonic 재생) 확인, 응답 지연 측정.

### M2 — Fish-Speech 실험 통합
1. 설치(별도 venv 권장, PyTorch/MPS): `speech.fish.audio/install` 절차, 모델 HF 다운로드.
2. `FishSpeechTtsBackend` 구현(CLI/파이썬 추론 → WAV bytes). 지연 로딩.
3. **맥북에어 실측**: 첫 문장 합성 지연, 메모리 사용, RTF. 상시 사용 가능선 판단.
4. 무겁거나 지연 크면 A/B 비교 결과만 기록하고 상시 사용 제외.

### M3 — 확정 및 정리
1. 청취 비교(Yuna/Supertonic/Fish) → 상업 배포 대상은 Supertonic 우선.
2. **Yuna 제거**: 확정 후 기본값을 선택된 프로바이더로, MacSayBackend는 코드에 남기되 기본 비활성(또는 제거).
3. `README`/`핸드오프 문서`/`docs` 갱신, `requirements` 반영.

---

## 리스크 & 트레이드오프
| 리스크 | 대응 |
|---|---|
| supertonic ↔ mlx 의존성 충돌 | 동시 임포트 스모크, 실패 시 `.tts-venv` 분리 |
| 최초 다운로드 vs 네트워크 차단 정책 | 사전 다운로드 단계 분리, 런타임은 `auto_download=False` |
| Fish-Speech 맥북에어 성능/메모리 | M2 실측 게이트, 실패 시 A/B만 |
| OpenRAIL-M 상업 조항 | 라이선스 원문 use-restriction 확인 후 배포 |
| 44.1kHz vs 프론트 재생 | 이미 sample_rate>0만 검증 → 무영향(스모크로 확인) |

## 검증 체크리스트
- [ ] `.voice-venv`에서 mlx + supertonic 동시 임포트 OK
- [ ] Supertonic 모델 캐시 후 오프라인 합성 OK
- [ ] `/api/config` tts 표기 전환 확인 (macos-say ↔ supertonic)
- [ ] 3종 백엔드 WAV 청취 비교본 생성
- [ ] 브라우저 음성 왕복 + 응답 지연 측정
- [ ] (M3) Yuna 제거 후 회귀 없음

## 미해결 — 승인 시 함께 확정
- 기본 화자: Supertonic **F1(여성)** 잠정 (상담 톤). 청취 후 조정.
- Fish-Speech를 별도 venv로 격리할지 여부(M2 착수 시 결정).
