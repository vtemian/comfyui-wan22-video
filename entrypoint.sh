#!/bin/bash
# Download weights before ComfyUI starts. The server scans model folders once, at launch.

set -euo pipefail

flag_on() {
    local value
    value="$(printf '%s' "${1:-0}" | tr '[:upper:]' '[:lower:]')"
    case "$value" in
        1|true|yes) return 0 ;;
        *) return 1 ;;
    esac
}

MODEL_DIR="${MODEL_DIR:-/runpod-volume/models}"

if ! flag_on "${SKIP_MODEL_DOWNLOAD:-0}"; then
    /opt/hub/download_models.sh "$MODEL_DIR"
    if flag_on "${DOWNLOAD_OPTIONAL_LORAS:-0}"; then
        MANIFEST=/opt/hub/models.optional.yaml /opt/hub/download_models.sh "$MODEL_DIR"
    fi
fi

exec /start.sh
