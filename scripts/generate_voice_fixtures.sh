#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'usage: %s --out DIR [--voice VOICE]\n' "$0" >&2
}

out=''
voice='Yuna'
while (($# > 0)); do
  case "$1" in
    --out) out=${2:?missing value for --out}; shift 2 ;;
    --voice) voice=${2:?missing value for --voice}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'error: unknown argument: %s\n' "$1" >&2; usage; exit 2 ;;
  esac
done

[[ -n "$out" ]] || { printf 'error: --out is required\n' >&2; usage; exit 2; }
[[ -x /usr/bin/say ]] || { printf 'error: /usr/bin/say is unavailable\n' >&2; exit 1; }
command -v ffmpeg >/dev/null || { printf 'error: ffmpeg is unavailable\n' >&2; exit 1; }
command -v ffprobe >/dev/null || { printf 'error: ffprobe is unavailable\n' >&2; exit 1; }
command -v python3 >/dev/null || { printf 'error: python3 is unavailable\n' >&2; exit 1; }

mkdir -p "$out"
for existing in "$out"/*; do
  [[ -e "$existing" ]] || continue
  case "$(basename "$existing")" in
    manifest.json|01.wav|02.wav|03.wav|04.wav|05.wav|06.wav|07.wav|08.wav|09.wav|10.wav) ;;
    *) printf 'error: refusing to overwrite unexpected output: %s\n' "$existing" >&2; exit 1 ;;
  esac
done

stage=$(mktemp -d "${TMPDIR:-/tmp}/voice-ko-fixtures.XXXXXX")
cleanup() { rm -rf "$stage"; }
trap cleanup EXIT INT TERM

texts=(
  '안녕하세요.'
  '오늘 상담을 시작하겠습니다.'
  '아침 인사를 연습합니다.'
  '천천히 또박또박 말합니다.'
  '지금 발음 상태를 확인합니다.'
  '짧은 문장을 읽어 봅니다.'
  '화면의 안내를 따라갑니다.'
  '필요하면 잠시 쉬어 갑니다.'
  '오늘 연습을 마치겠습니다.'
  '다음 단계로 이동합니다.'
)

: > "$stage/utterances.tsv"
for index in "${!texts[@]}"; do
  id=$(printf '%02d' "$((index + 1))")
  aiff="$stage/$id.aiff"
  wav="$stage/$id.wav"
  /usr/bin/say -v "$voice" -o "$aiff" "${texts[$index]}"
  ffmpeg -hide_banner -loglevel error -y -i "$aiff" -ac 1 -ar 16000 -c:a pcm_s16le "$wav"
  duration=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$wav" | tr -d '\r\n')
  printf '%s\t%s\t%s\n' "$id.wav" "${texts[$index]}" "$duration" >> "$stage/utterances.tsv"
done

python3 - "$stage/utterances.tsv" "$stage/manifest.json" "$voice" <<'PY'
import json
import sys
from pathlib import Path

rows = []
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    filename, text, duration = line.split("\t")
    rows.append({"file": filename, "expected_text": text, "duration_seconds": float(duration)})
manifest = {
    "schema_version": 1,
    "coverage_label": "deterministic compatibility coverage; not natural-speaker quality evidence",
    "source": {"generator": "/usr/bin/say", "voice": sys.argv[3], "normalizer": "ffmpeg"},
    "audio": {"codec": "pcm_s16le", "sample_rate": 16000, "channels": 1},
    "utterances": rows,
}
if len(rows) != 10 or len({row["file"] for row in rows}) != 10:
    raise SystemExit("manifest must contain exactly 10 unique utterances")
Path(sys.argv[2]).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

for number in $(seq 1 10); do
  index=$(printf '%02d' "$number")
  mv -f "$stage/$index.wav" "$out/$index.wav"
done
mv -f "$stage/manifest.json" "$out/manifest.json"
printf 'generated 10 deterministic Korean fixtures in %s\n' "$out"
