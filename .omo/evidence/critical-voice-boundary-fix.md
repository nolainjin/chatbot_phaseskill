# Critical voice boundary fix evidence

Started: 2026-07-22T01:51:27+09:00
Scope: `app/voice_api.py`, `app/voice_boundary.py`, `tests/test_voice_api.py`, and this redacted evidence file.

## Baseline

- Repo: `/Volumes/부부공용/worknote/lmwiki-chatbot`
- Branch: `agent/contextual-reply-buttons`
- HEAD: `241fa3e0c144f659760beb519a2cd60eda9c0dee`
- Upstream: `origin/agent/contextual-reply-buttons`
- Runtime: Python 3.14.5, FastAPI 0.139.0, Starlette 1.3.1, AnyIO from the repo virtualenv, Node v25.2.1, ffmpeg 7.1.1.
- Pre-existing owned-path state: `scripts/voice-ui-test.mjs` has six dirty assertion lines from another task. It will not be edited or staged unless required by this fix.
- Pre-existing unrelated dirty and untracked files, `.debug-journal.md`, and `screenshots/` are protected and will not be changed, removed, reset, stashed, or staged.
- Debug references read: Python runtime, Node runtime, Playwright CLI, setup, investigation, TDD fix, manual QA, cleanup/final verification.

## Hypotheses

1. H1: browser WebM/MP4 is rejected before the provider because `transcribe()` calls `decode_wav_duration_ms(payload)` on the original container. Evidence needed: real ffmpeg WebM/MP4 requests return `400 invalid_audio` and the fake provider is not called.
2. H2: a non-loopback ASGI client is accepted because neither voice endpoint inspects `request.client.host`. Evidence needed: a TestClient with a documentation-range remote address reaches each fake provider instead of returning `403 local_only_violation`.
3. H3: declared oversized multipart bodies are parsed before application code because FastAPI `Form`/`File` dependencies own parsing and the route only caps `audio.read()`. Evidence needed: a tiny malformed multipart request with an over-limit `Content-Length` does not return the stable `413 audio_too_large` contract.
4. H4: the synchronous transcription provider runs in the async route thread because it is called directly. Evidence needed: a fake provider observes an active async library context instead of a worker thread.

## Artifacts and cleanup

- The evidence file is an authorized deliverable and will be committed.
- pytest temporary media is process-local or under pytest-managed temporary directories; no raw audio will be copied into evidence.
- Any T9 server/sidecar/browser processes must be terminated and port 8767 rechecked before commit.

## Findings

### Red phase — 2026-07-22T01:54+09:00

Command: `VOICE_NETWORK_DENY=1 .venv/bin/python -m pytest -q tests/test_voice_api.py -k 'browser_mediarecorder or blocking_provider or non_loopback or declared_oversize'`

Result: `6 failed, 29 deselected, 1 warning in 1.66s`.

- WebM and MP4: expected `200`, observed `400`; confirms H1 with real ffmpeg-generated non-silent containers.
- Async boundary: expected provider outside async context, observed `True`; confirms H4.
- Remote transcribe and synthesize: expected `403`, observed `200` even with `X-Forwarded-For: 127.0.0.1`; confirms H2 and proves forwarding headers must remain untrusted.
- Declared oversize: expected `413`, observed multipart parser warning followed by `400`; confirms H3 and shows parsing happened before the cap.
- No raw audio bytes or secrets are recorded in this evidence.

### Green phase — 2026-07-22T02:09+09:00

- Focused boundary regression: `VOICE_NETWORK_DENY=1 .venv/bin/python -m pytest -q tests/test_voice_api.py -k 'browser_mediarecorder or blocking_provider or non_loopback or declared_oversize'` -> `6 passed, 33 deselected, 1 warning in 2.35s`.
- Full voice API: `VOICE_NETWORK_DENY=1 .venv/bin/python -m pytest -q tests/test_voice_api.py` -> `39 passed, 1 warning in 1.20s`.
- Full pytest: `VOICE_NETWORK_DENY=1 .venv/bin/python -m pytest -q` -> `272 passed, 1 warning in 8.91s`.
- Hostile browser events: `node scripts/voice-ui-test.mjs --scenario hostile-events` -> all 11 named scenarios passed; the pre-existing script diff was neither edited nor staged.
- Compile gate: `.venv/bin/python -m compileall -q app tests` -> exit 0.
- Whitespace gate before evidence update: `git diff --check` -> exit 0.
- Pre-existing listener `Python` PID 85144 on `127.0.0.1:8766` was observed and left running; no server, sidecar, or browser process was started or stopped by this finish pass.

### Multipart Content-Length overhead regression — 2026-07-22T02:18+09:00

- The pre-parse request cap now allows 64 KiB of bounded multipart framing overhead above the 10 MiB file limit.
- The exact per-file cap remains `audio.read(MAX_AUDIO_BYTES + 1)` followed by a `413 audio_too_large` response when the file payload exceeds 10 MiB.
- Red proof: the exactly 10 MiB multipart file returned `413` before the fix while the malformed request declared above 10 MiB plus 64 KiB still returned `413` before parsing.
- Focused boundary tests: `VOICE_NETWORK_DENY=1 .venv/bin/python -m pytest -q tests/test_voice_api.py::test_transcribe_allows_exact_file_limit_with_multipart_overhead tests/test_voice_api.py::test_transcribe_rejects_declared_body_over_multipart_limit_before_parse` -> `2 passed, 1 warning in 0.83s`.
- Full voice API: `VOICE_NETWORK_DENY=1 .venv/bin/python -m pytest -q tests/test_voice_api.py` -> `40 passed, 1 warning in 1.67s`.
