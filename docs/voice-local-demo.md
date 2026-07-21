# 로컬 음성 데모 런북

이 문서는 `lmwiki-chatbot`의 로컬 전용 음성 데모를 재현하는 절차다. 기본 제품 실행은 text-only이며, T9 데모 명령만 짧은 프로세스 안에서 기존 local provider adapter를 FastAPI voice 경로에 연결한다. 원격 STT/TTS, 클라우드 `SpeechRecognition`, 음성 원본 저장은 사용하지 않는다.

## 선택 프로파일

- STT: Qwen3-ASR 0.6B 8-bit / MLX-Audio
- TTS: macOS `/usr/bin/say -v Yuna`, ffmpeg로 22050 Hz mono PCM WAV 변환
- loopback: FastAPI는 `http://127.0.0.1:8767`, sidecar는 매 요청마다 예약되는 `127.0.0.1` 포트
- 모델 캐시: `<repo>/.voice-model-cache/` (Git ignored); T2에서 검증한 Hugging Face snapshot만 사용
- 명시적 fallback: `VOICE_STT_PROVIDER=whisper.cpp` + `VOICE_WHISPER_CPP_MODEL=<local GGML model>` + macOS `say`
- 현재 호스트에서 whisper.cpp GGML 모델과 Supertonic 3 가중치는 `UNAVAILABLE`이며, fallback은 자동 원격 다운로드를 하지 않는다.

T2의 선택 gate는 network-deny에서 10/10 non-empty, warm RTF ≤ 1.0, peak RSS ≤ 8 GiB를 요구했다. 합성 WAV의 CER/음성 품질은 자연 발화 품질 증거가 아니라 재현 가능한 compatibility check다.

## 사전 조건

```bash
cd /Volumes/부부공용/worknote/lmwiki-chatbot
test -x .venv/bin/python
test -x .voice-venv/bin/python
test -d .voice-model-cache
test -d scripts/gui-smoke/node_modules
ffprobe -version >/dev/null
```

권한 문제가 남아 있으면 Chromium의 localhost microphone 권한을 초기화한 뒤 다시 연다. 자동화는 다음 fake-media 플래그를 사용한다.

```text
--use-fake-ui-for-media-stream
--use-fake-device-for-media-stream
--use-file-for-fake-audio-capture=tests/fixtures/voice-ko/01.wav
```

이 플래그의 성공은 fake media 증거다. physical microphone 증거로 해석하지 않는다. 현재 자동화 환경의 physical microphone proof는 `UNAVAILABLE`이다.

## 원 커맨드 데모

아래 명령 하나가 FastAPI, local sidecar, 선택 모델, fake-media Chromium smoke, 합성 WAV fixture 10회 cycle, TTS WAV ffprobe, malformed input, text-only recovery, JSON/TXT/PNG 증적을 실행하고 소유한 프로세스와 임시 디렉터리를 정리한다.

```bash
VOICE_ENABLED=true ./scripts/voice_demo_smoke.sh --browser chromium --cycles 10 --network-deny
```

### T9 복구 검증 결과 (2026-07-22)

복구 세션에서는 전체 10회 실행을 반복하지 않고 다음 bounded 명령만 실행했다.

```bash
VOICE_ENABLED=true ./scripts/voice_demo_smoke.sh --browser chromium --cycles 1 --network-deny
```

- 결과: `bounded_pass`; local cycle 1/1, network-deny PASS, fake-media browser 시나리오 11개 PASS, malformed audio `400/invalid_audio`, text-only recovery PASS.
- benchmark: Qwen3-ASR cold 8416.8ms, warm 188.8ms, warm RTF 0.1047, peak RSS 0.509 GiB, CER 0.0, non-empty 1.0.
- full 10-cycle gate: `NOT_RUN` — 1회 bounded 검증으로 10회 연속 성공을 주장하지 않는다.
- physical microphone: `UNAVAILABLE` — Chromium fake-media만 사용했다.
- 초기 실행에서 발견된 T9 blocker는 임시 작업 디렉터리에서 inline Playwright import가 `scripts/gui-smoke/node_modules`를 찾지 못한 것이었고, `scripts/voice_demo_smoke.sh`가 해당 dependency 디렉터리에서 import하도록 최소 수정했다. `scripts/voice_provider_benchmark.py`의 `[ -x ]` 검사는 통과했으며 권한 문제는 아니었다.

주요 결과:

```text
.omo/evidence/task-9-voice-local-demo.json
.omo/evidence/task-9-voice-local-demo.txt
.omo/evidence/task-9-voice-local-demo.png
```

사이드카는 `VOICE_PROVIDER_PYTHON`으로 지정한 `.voice-venv`에서 실행된다. demo launcher는 `VOICE_PROVIDER_PYTHON`, `VOICE_STT_PROVIDER`, `VOICE_TTS_VOICE`, `VOICE_TEMP_ROOT`를 sidecar에 전달하며, network-deny일 때 Hugging Face offline 환경도 함께 설정한다. FastAPI의 일반 text-only 시작 명령은 제품 기본값을 보존하므로 voice provider를 자동 상주시켜서는 안 된다.

선택 profile을 직접 확인하려면 다음을 실행한다.

```bash
VOICE_NETWORK_DENY=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .voice-venv/bin/python scripts/voice_provider_benchmark.py \
  --fixtures tests/fixtures/voice-ko \
  --out /tmp/task-9-qwen-benchmark.json
```

## 10회 cycle 계약

각 cycle은 `voice-demo-N` session으로 분리되어 다음 순서를 확인한다.

```text
start → synthetic recording ≥800 ms → stop/final dataavailable → local STT
→ transcript review/confirm → existing /api/chat exactly once → optional local TTS
```

증적에는 attempt ID, duration, latency, provider/model, peak RSS, RTF, CER, WAV validity, error code만 남긴다. transcript 본문, audio bytes, provider request body, secret, model weight는 남기지 않는다. 브라우저 fake smoke가 final `dataavailable` 순서·review gate·stale callback·중복 전송·TTS fallback을 검증하고, local cycle은 실제 synthetic WAV를 local sidecar에 보내 STT/chat/TTS를 검증한다.

## 실패 복구

소유한 sidecar를 끊는 probe는 다음처럼 실행한다. sidecar kill이 관찰되면 결과는 `provider_unavailable` 또는 `provider_timeout`으로 분류되어야 하며, raw 500이나 성공으로 위장하면 안 된다.

```bash
VOICE_ENABLED=true ./scripts/voice_demo_smoke.sh \
  --browser chromium --cycles 1 --network-deny --kill-sidecar
```

텍스트-only 복구는 sidecar를 시작하지 않고 기존 bounded smoke를 실행한다.

```bash
VOICE_ENABLED=false ./scripts/smoke_local.sh
```

사용자 권한을 거부하거나 실제 기기가 종료된 경우에도 text input은 남아야 한다. TTS가 실패해도 assistant text는 롤백하지 않는다.

## 증거 해석과 cleanup

- `browser_fake_media`는 fake Chromium 결과이며 physical microphone 수치에 합산하지 않는다.
- `benchmark`는 선택 provider의 cold/warm latency, RTF, RSS, CER, non-empty rate를 담는다.
- `cycles.rows`에는 raw audio가 아니라 metadata만 있다.
- `failure_probe`, `malformed_input_probe`, `text_only_recovery`는 분류된 HTTP 결과와 회복 경계를 담는다.
- `voice-sidecar-*` 임시 디렉터리, TTS 임시 WAV, server/browser context는 종료 trap으로 정리된다.
- 작업 시작 전부터 존재한 uvicorn/Playwright MCP 등의 unrelated process는 소유하지 않으므로 건드리지 않는다.

검증 후 기대하는 scope는 `docs/voice-local-demo.md`, `scripts/voice_demo_smoke.sh`, 그리고 T9 evidence 3개뿐이다. 기존 dirty tracked/untracked 파일과 `screenshots/`는 보존한다.
