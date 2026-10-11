#!/bin/bash
#
# Download the models listed in models.yaml into a ComfyUI models directory.
#
# Usage: ./download_models.sh <models_dir>
#   models_dir  ComfyUI models directory, for example /runpod-volume/models
#
# Set MANIFEST to read a different file (default: models.yaml beside this script).
# Set DRY_RUN=1 to print the targets and exit without fetching anything.
# Set MAX_ATTEMPTS to change how many times a stalled transfer is resumed (default 20).
# Set HF_TOKEN to send a Hugging Face bearer token. Public files do not need one.
#
# Resumes partial downloads and skips files that already reach their manifest size.
# Refuses a manifest that names an audio model this template does not ship.

set -euo pipefail

MODELS_DIR="${1:?usage: ./download_models.sh <models_dir>}"
MANIFEST="${MANIFEST:-$(dirname "$0")/models.yaml}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-20}"
DRY_RUN="${DRY_RUN:-0}"

if grep -Eiq 'mmaudio|bigvgan|ace[-_]step' "$MANIFEST"; then
    echo "refusing manifest that names an audio model: $MANIFEST" >&2
    exit 1
fi

DOWNLOADS="$(mktemp "${TMPDIR:-/tmp}/wan22_downloads.XXXXXX")"
trap 'rm -f "$DOWNLOADS"' EXIT

file_size() {
    wc -c 2>/dev/null < "$1" || echo 0
}

python3 - "$MANIFEST" <<'PY' > "$DOWNLOADS"
import re
import sys

manifest = sys.argv[1]
entry = {}
for line in open(manifest, encoding="utf-8"):
    match = re.match(r"^(url|path|size_gb):\s*(.+)$", line.strip())
    if not match:
        continue
    entry[match.group(1)] = match.group(2).strip().strip('"')
    if len(entry) < 3:
        continue
    print(f"{entry['url']}\t{entry['path']}\t{entry['size_gb']}")
    entry = {}
PY

TOTAL=$(awk -F'\t' '{s+=$3} END {printf "%.2f", s}' "$DOWNLOADS")
COUNT=$(wc -l < "$DOWNLOADS" | tr -d ' ')

echo "=== text-to-video weights ==="
echo "$COUNT files, ${TOTAL}GB, into $MODELS_DIR"
echo ""

if [ "$DRY_RUN" != "0" ]; then
    while IFS=$'\t' read -r url path size; do
        echo "would get  $MODELS_DIR/$path (${size}GB)"
        echo "           $url"
    done < "$DOWNLOADS"
    echo ""
    echo "=== dry run, nothing downloaded ==="
    exit 0
fi

while IFS=$'\t' read -r _ path _; do
    mkdir -p "$MODELS_DIR/$(dirname "$path")"
done < "$DOWNLOADS"

auth=()
if [ -n "${HF_TOKEN:-}" ]; then
    auth=(-H "Authorization: Bearer ${HF_TOKEN}")
fi

while IFS=$'\t' read -r url path size; do
    target="$MODELS_DIR/$path"
    # Compare against the manifest size, not mere existence. A zero-byte
    # placeholder with the right name must not count as a finished download.
    expected=$(awk -v g="$size" 'BEGIN {e = g * 1000000000 * 0.9; printf "%d", (e < 1 ? 1 : e)}')
    actual=$(file_size "$target")
    if [ "$actual" -ge "$expected" ]; then
        echo "have  $path"
        continue
    fi
    if [ "$actual" -gt 0 ]; then
        echo "part  $path ($(awk -v a="$actual" 'BEGIN {printf "%.1f", a/1000000000}')GB of ${size}GB, resuming)"
    fi
    echo "get   $path (${size}GB)"

    # curl's own --retry does not cover a connection dropped mid-transfer.
    attempt=1
    until curl -fL --retry 5 --retry-delay 5 --retry-all-errors -C - --progress-bar \
        "${auth[@]}" -o "$target" "$url"; do
        actual=$(file_size "$target")
        [ "$actual" -ge "$expected" ] && break
        if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
            echo "fail  $path after $attempt attempts" >&2
            exit 1
        fi
        attempt=$((attempt + 1))
        echo "retry $path attempt $attempt"
        sleep 5
    done
done < "$DOWNLOADS"

echo ""
echo "=== done ==="
