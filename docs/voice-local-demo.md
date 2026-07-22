# 로컬 음성 데모 런북

이 문서는 `lmwiki-chatbot`의 로컬 전용 턴 기반 음성 데모를 실행하고 검증하는
절차다. 기본 제품 실행은 text-only이고, 별도 local voice launcher만 기존 local
provider adapter를 FastAPI voice 경로에 연결한다. 원격 STT/TTS, 클라우드
`SpeechRecognition`, 음성 원본 저장은 사용하지 않는다.

## 두 종류의 mode

- `Chat Mode`와 `Voice Mode`는 사용자가 텍스트 또는 음성으로 상호작용하는
  클라이언트 `interactionMode`(`interaction mode`)다.
- coaching과 intake는 지식팩과 `/api/config.mode`가 정하는 대화 내용의 서버
  `contentMode`(`content mode`)다. interaction mode와 독립적이다.
- Chat/Voice는 같은 `session_id`, `session_token`, participant, turn count,
  session/history, message DOM과 canonical `/api/chat`을 공유한다. Voice 전용
  conversation endpoint나 별도 history는 없다.
- voice capability 또는 브라우저의 `getUserMedia`/`MediaRecorder`가 없으면
  `Chat Mode`로 fail-closed한다.

## 선택 프로파일

- STT: Qwen3-ASR 0.6B 8-bit / MLX-Audio; `/api/config` representation은
  `qwen3-asr-0.6b-8bit`
- TTS: macOS `say` Yuna (`/usr/bin/say -v Yuna`), ffmpeg로 22050 Hz mono PCM
  WAV 변환; `/api/config` representation은 `macos-say:Yuna`
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

## 대화형 local voice launcher

먼저 side effect 없이 launcher 인자와 기본 bind를 확인한다.

```bash
.venv/bin/python scripts/run_local_voice.py --help
```

실제 로컬 provider를 연결해 실행한다.

```bash
.venv/bin/python scripts/run_local_voice.py --host 127.0.0.1 --port 8767
```

브라우저에서 localhost URL http://127.0.0.1:8767/ 을 연다. launcher는
`VOICE_ENABLED=true`, `VOICE_NETWORK_DENY=1`, `HF_HUB_OFFLINE=1`,
`TRANSFORMERS_OFFLINE=1`을 적용하며 non-loopback host를 거부한다. 모델은 기존
`.voice-model-cache/` snapshot만 읽고 실행 중 다운로드나 remote/cloud fallback을
허용하지 않는다. 종료할 때는 실행한 터미널에서 `Ctrl-C`를 한 번 누르고 provider
정리가 끝날 때까지 기다린다.

### Voice Mode 한 턴

1. `Voice Mode`를 선택하고 녹음을 명시적으로 시작한다.
2. 800ms 이상 녹음한 뒤 중지를 누른다. 브라우저의 최종 순서는
   `record → stop 요청(녹음 ≥800ms) → final dataavailable → stop`이다.
3. local STT가 끝나면 editable transcript review에서 전사문을 고친다. 이 review를
   확인하기 전에는 `/api/chat`이 호출되지 않는다.
4. 확인을 누르면 canonical `/api/chat`을 정확히 한 번 호출한다.
5. assistant text를 먼저 표시하고 auto local TTS attempt를 수행한다. TTS 성공,
   실패 또는 fallback 뒤 상태는 `ready`가 된다.
6. 다음 녹음은 사용자가 버튼을 눌러 명시적으로 시작한다. 마이크를 자동으로 다시
   켜지 않는다.

브라우저가 자동 재생을 `NotAllowedError`로 막으면 assistant text와 확인된 응답은
그대로 보존하고, 한 번 누를 수 있는 `응답 듣기` 버튼을 표시한다. 사용자가 버튼을
누르지 않거나 재생이 다시 실패해도 `ready`로 복구되어 Chat 또는 다음 Voice 턴을
시작할 수 있다.

### mode 전환과 응답 보존

`Chat Mode`와 `Voice Mode`를 전환하면 permission 대기, recorder, STT, editable
review와 TTS 같은 미확정 voice 작업을 정리하고 이전 interaction epoch의 callback을
무시한다. Chat text draft, session/token, turn count와 기존 history는 유지한다.

사용자가 review를 확인해 이미 `/api/chat`으로 보낸 요청은 mode 전환으로 취소하지
않는다. 응답이 도착하면 공유 assistant text/history에 표시하되, 이전 Voice epoch의
focus 이동이나 auto-TTS 같은 stale side effect만 억제한다.

## Phase 1 OUT

아래 기능은 이번 턴 기반 데모의 범위 밖이며 구현되었다고 해석하면 안 된다.

- `continuous listening`
- `VAD` 또는 `silence auto-stop` (60초 최대 녹음 safety cap과는 별개)
- `auto-send`
- `wake word`
- `duplex` streaming
- `barge-in`
- `auto mic restart`

## 원 커맨드 데모

아래 명령 하나가 FastAPI, local sidecar, 선택 모델, fake-media Chromium smoke, 합성 WAV fixture 10회 cycle, TTS WAV ffprobe, malformed input, text-only recovery, JSON/TXT/PNG 증적을 실행하고 소유한 프로세스와 임시 디렉터리를 정리한다.

```bash
VOICE_ENABLED=true ./scripts/voice_demo_smoke.sh --browser chromium --cycles 10 --network-deny --kill-sidecar
```

### T9 최종 검증 결과 (2026-07-22)

사전 red 증거는 다음 실패를 기록했다.

```text
FAIL: local cycle 2 did not return a session token
```

원인은 `app/main.py`가 첫 요청에만 `session_token`을 응답하는 계약인데, launcher가 cycle 2의 빈 응답값으로 보존 중인 token을 무조건 덮어쓴 것이었다. 수정 후에는 응답 token이 non-empty일 때만 갱신하고, 다음 인증 요청에 사용할 token이 없을 때만 실패한다.

```bash
VOICE_ENABLED=true ./scripts/voice_demo_smoke.sh \
  --browser chromium --cycles 10 --network-deny --kill-sidecar
```

- 결과: `PASS`; local cycle 10/10 consecutive, `full_10_cycle_gate=PASS`, network-deny PASS, fake-media browser 시나리오 11개 PASS, malformed audio `400/invalid_audio`, text-only recovery PASS.
- benchmark: Qwen3-ASR cold 8941.1ms, warm 182.4ms, warm RTF 0.1012, peak RSS 0.649 GiB, CER 0.0, non-empty 1.0.
- sidecar kill: `503 / provider_unavailable`, `sidecar_killed=true`, classified PASS.
- hostile-events race coverage는 T8가 소유·검증하므로 T9 launcher가 중복 실행하지 않는다. T9는 `voice-local-smoke` fake-media gate와 local cycle, malformed input, sidecar kill, text-only recovery를 실행한다.
- physical microphone: `UNAVAILABLE` — Chromium fake-media만 사용했다.
- cleanup: launcher trap으로 FastAPI/owned sidecar/voice temp root를 정리했고, `8767` listener는 남지 않았다. pre-existing `8766` process와 unrelated dirty/untracked 파일은 건드리지 않았다.

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

text-only 복구는 sidecar를 시작하지 않고 기존 bounded smoke를 실행한다.

```bash
VOICE_ENABLED=false ./scripts/smoke_local.sh
```

사용자 권한을 거부하거나 실제 기기가 종료된 경우에도 text input은 남아야 한다.
Chromium에서 권한이 잘못 저장되었으면 `127.0.0.1:8767`의 사이트 정보에서 microphone
권한을 초기화하고 탭을 다시 연 뒤, `Voice Mode`에서 사용자가 다시 녹음을 시작한다.
권한 초기화는 자동화의 fake-media 허용과 별개다.

provider/cache preflight 실패 또는 실행 중 `provider_unavailable` /
`provider_timeout`이 발생하면 assistant text를 지우지 말고 `Chat Mode`로 전환한다.
음성 launcher를 종료한 뒤 README의 기존 text-only 명령으로 서버를 실행하면 sidecar
없이 같은 채팅 경로를 계속 사용할 수 있다. TTS가 실패해도 assistant text는
롤백하지 않는다.

## 증거 등급 분리

세 증거는 서로 대체하지 않으며 결과를 합쳐서 과장하지 않는다.

1. `fake-media`: Chromium fake device로 UI 순서, final chunk, editable review,
   exactly-once chat, mode switch와 TTS fallback을 검증한다. 실제 마이크나 실제 local
   provider의 음질 증거가 아니다.
2. `actual local provider`: 저장된 synthetic fixture를 network deny 아래 local
   sidecar의 STT/TTS에 전달해 profile, latency, HTTP 분류와 WAV validity를 검증한다.
   physical microphone 증거가 아니며 raw audio/transcript는 evidence에 남기지 않는다.
3. `physical microphone`: 실제 장치 권한, 녹음과 청취를 사람이 별도로 확인한 증거다.
   이 실행에서 `physical microphone: UNAVAILABLE`이며, `UNAVAILABLE`은 PASS가 아니다.

## 증거 해석과 cleanup

- `browser_fake_media`는 fake Chromium 결과이며 physical microphone 수치에 합산하지 않는다.
- `benchmark`는 선택 provider의 cold/warm latency, RTF, RSS, CER, non-empty rate를 담는다.
- `cycles.rows`에는 raw audio가 아니라 metadata만 있다.
- `failure_probe`, `malformed_input_probe`, `text_only_recovery`는 분류된 HTTP 결과와 회복 경계를 담는다.
- `voice-sidecar-*` 임시 디렉터리, TTS 임시 WAV, server/browser context는 종료 trap으로 정리된다.
- 작업 시작 전부터 존재한 uvicorn/Playwright MCP 등의 unrelated process는 소유하지 않으므로 건드리지 않는다.

T9 검증 당시 기대 scope는 `docs/voice-local-demo.md`, `scripts/voice_demo_smoke.sh`,
그리고 T9 evidence 3개였다. 기존 dirty tracked/untracked 파일과 `screenshots/`는
보존한다.
