# TTS 업그레이드 리서치 — Supertonic 3 + Fish-Speech

작성일: 2026-07-22
목표: 현재 macOS `say`(Yuna) TTS를 더 자연스러운 로컬 뉴럴 TTS로 교체. **Supertonic 3**과 **Fish-Speech** 두 백엔드를 함께 붙여 스위치로 A/B 비교. Yuna는 테스트 후 제거.

---

## 1. 후보 비교 요약

| 항목 | Yuna (현행) | **Supertonic 3** | **Fish-Speech / Fish Audio** | Typecast |
|---|---|---|---|---|
| 방식 | macOS `say`+ffmpeg | ONNX (온디바이스) | PyTorch (온디바이스) | 클라우드 API |
| 오프라인 | ✅ | ✅ 완전 | ✅ 가능(무거움) | ❌ |
| 한국어 | 시스템 음성 | ✅ 31개 언어 | ✅ 80+ 언어(한국어 Tier 2) | ✅ |
| 모델 크기 | - | **~400MB** | 0.5B~**4B** (수 GB) | - |
| 출력 | 22.05kHz WAV | **44.1kHz 16bit WAV** | (미명시, 고품질) | - |
| 맥북에어 적합성 | ✅ 매우 가벼움 | ✅ 가벼움·빠름 | ⚠️ 무거움(RAM 부담) | - |
| 라이선스 | 시스템 | **MIT+OpenRAIL-M(관대)** | ⚠️ **CC-BY-NC-SA(비상업)** | 유료 |
| 음성 복제 | ❌ | ✅ (voice style JSON) | ✅ (강점) | ✅ |
| 자연스러움 | 낮음 | 높음 | **매우 높음** | 매우 높음 |

**타입캐스트**: 클라우드 구독/API 유료 서비스 → 로컬 오프라인 정책과 맞지 않아 제외.

---

## 2. Supertonic 3 상세

- **설치**: `pip install supertonic` (서버 기능은 `pip install 'supertonic[serve]'`)
- **Python API** (매우 단순):
  ```python
  from supertonic import TTS
  tts = TTS(auto_download=True)
  style = tts.get_voice_style(voice_name="M1")   # 기본 M1~M5, F1~F5
  wav, duration = tts.synthesize(
      "회의는 잠시 후에 시작되며 모두가 자리에 앉아 기다립니다.",
      voice_style=style, lang="ko", total_steps=8, speed=1.05,
  )
  tts.save_audio(wav, "output.wav")
  ```
- **모델**: ~400MB, 최초 1회 `~/.cache/supertonic3/`에 자동 다운로드. 이후 완전 오프라인.
- **출력**: 스튜디오급 44.1kHz 16bit WAV → 현재 파이프라인 그대로 수용(아래 §4).
- **음성 복제**: `get_voice_style_from_path("voices/my_voice.json")`로 커스텀 화자.
- **라이선스**: 코드 MIT / 모델 OpenRAIL-M(연구·상용 대체로 허용, 책임있는 사용 조항).
- **속도**: 1000+ chars/sec, Apple Silicon CPU에서 실용적.
- **평가**: 맥북에어 로컬 TTS로 **최적**. 가볍고 빠르고 라이선스 관대, 통합 쉬움.

## 3. Fish-Speech / Fish Audio 상세

- **현재 모델 계보**: fish-speech 1.5(13개 언어) → OpenAudio S1-mini → **Fish Audio S2 Pro (4B 파라미터)**.
- **한국어**: 지원(Tier 2). 자연스러움·감정표현·음성복제 품질이 후보 중 최상급.
- **시스템 요구**: 원 문서 기준 VRAM 12GB+ 권장(1.5), S2 Pro는 4B로 더 무거움. Apple Silicon(MPS) 지원은 추가됐으나 **통합메모리 맥북에어에는 부담**. 실측 필요.
- **설치**: PyTorch 기반, https://speech.fish.audio/install/ 참조. MPS 빌드 또는 CPU. Supertonic보다 셋업 복잡.
- **성능**: NVIDIA H200 기준 RTF 0.195(≈실시간의 5배 빠름). 맥북에어 CPU/MPS에서는 훨씬 느릴 것 → **응답 지연 리스크**.
- **라이선스**: ⚠️ **CC-BY-NC-SA 4.0 / FISH AUDIO RESEARCH LICENSE — 비상업적 전용**. "위반 시 조치" 명시. 상업적 사용은 별도 계약 필요.
- **평가**: 품질 최상이나 (1) 무겁고 느릴 수 있음, (2) **비상업 라이선스 제약**, (3) 설치 복잡. A/B 비교용으로는 가치 있으나 상시 운영엔 리스크.

---

## 4. 현재 아키텍처 통합 지점 (교체 용이성 분석)

핵심: 코드가 이미 **TTS 백엔드 교체 가능**하게 설계됨.

- `voice_runtime/adapters.py`
  - `TtsBackend` Protocol: `synthesize(self, text: str) -> bytes` (WAV 바이트 반환)
  - `MacSayBackend`가 현재 유일 구현 (say→aiff→ffmpeg→22.05kHz wav)
  - `build_backends()`가 TTS를 **항상 MacSayBackend로 고정** (STT만 분기) ← 여기에 분기 추가
- `app/voice_api.py` `/api/voice/synthesize`: `synthesis_provider.synthesize(text)` 호출 후 `validate_synthesized_audio()`
- **샘플레이트 제약 없음**: `validate_synthesized_audio`는 `sample_rate > 0`만 검사(16kHz 강제는 STT 입력 정규화 경로에만 적용). → Supertonic 44.1kHz, Fish-Speech 출력 모두 그대로 수용.
- **프론트(static/tts.js)**: 서버가 주는 WAV를 재생만 하므로 **수정 불필요**.

### 통합 설계 개요 (구현은 승인 후)
1. `.voice-venv`에 백엔드별 의존성 설치 (`supertonic`, Fish-Speech PyTorch 스택)
2. `voice_runtime/adapters.py`에 `SupertonicTtsBackend`, `FishSpeechTtsBackend` 추가 — 각 `synthesize(text)->WAV bytes`
3. `build_backends()`에 `VOICE_TTS_PROVIDER` env 분기 (`macos-say` | `supertonic` | `fish-speech`)
4. `run_local_voice.py`에 프로바이더 스위치 노출 (기본값·CLI 플래그)
5. 모델 최초 다운로드는 `HF_HUB_OFFLINE` 일시 해제 후 캐시 → 이후 오프라인
6. `/api/config`에 현재 tts 표기 반영, A/B 테스트 → 최종 선택 후 Yuna 제거

---

## 5. 권장안 & 미결 결정사항

**권장 진행 순서**
1. **Supertonic 3 먼저 통합** (가볍고 라이선스 관대, 통합 쉬움) → Yuna와 A/B
2. **Fish-Speech는 실험적 2차** — 맥북에어 실측(속도·메모리) 후 상시 사용 여부 판단
3. 둘 다 스위치로 남겨 비교 → 만족스러운 쪽으로 확정, Yuna 제거

**사용자 결정 (2026-07-22 확정)**
- [x] **상업적 사용 여부**: → **상업 가능성 있음**. 따라서:
  - **Supertonic 3 = 상시 운영 후보** (OpenRAIL-M, 상업 허용 — 단 책임있는 사용 조항 존재, 원문 확인 권장)
  - **Fish-Speech = A/B 비교용만** (CC-BY-NC-SA 비상업 전용, 상업 배포 부적합)
  - 최종 상업 배포는 Supertonic 위주
- [ ] Fish-Speech 응답 지연(맥북에어에서 수 초 가능성)을 감수하고 A/B에 포함 → 계획상 2차 실험
- [ ] Supertonic 기본 화자(M1~M5/F1~F5) 중 선호 톤, 또는 음성 복제로 커스텀 화자 사용할지 → 구현 후 청취 결정

---

## 6. 출처
- Supertonic: https://github.com/supertone-inc/supertonic , https://github.com/supertone-inc/supertonic-py , https://huggingface.co/Supertone/supertonic-3
- Fish-Speech: https://github.com/fishaudio/fish-speech , https://huggingface.co/fishaudio/fish-speech-1.5 , 라이선스 논의 https://github.com/fishaudio/fish-speech/discussions/1001
- 로컬 TTS 비교(2026): https://www.murmurtts.com/blog/best-local-tts-models-2026
